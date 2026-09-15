import streamlit as st
import datetime
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
import requests
import google.generativeai as genai
from streamlit_geolocation import streamlit_geolocation

# ReportLab PDF 생성용 라이브러리
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, String

# ==========================================
# 🛠️ [고정 설정] 발송 및 수신 메일 계정 설정 (Gmail 적용 완료)
# ==========================================
FIXED_SMTP_SERVER = "smtp.gmail.com"
FIXED_SMTP_PORT = 465
FIXED_SENDER_EMAIL = "jechanam@gmail.com"        
FIXED_SENDER_PASSWORD = "emhvjdvudtlcddeq"    
FIXED_RECEIVER_EMAIL = "jech@anamt.co.kr"     # 👈 보고서를 받을 실제 메일 주소로 나중에 변경하세요!

# --- 0. 한글 폰트 강제 등록 (리눅스 서버 / 윈도우 환경 자동 분기) ---
try:
    linux_font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    windows_font_path = 'C:/Windows/Fonts/malgun.ttf'

    if os.path.exists(linux_font_path):
        pdfmetrics.registerFont(TTFont('NanumGothic', linux_font_path))
        KOREAN_FONT = 'NanumGothic'
    elif os.path.exists(windows_font_path):
        pdfmetrics.registerFont(TTFont('Malgun', windows_font_path))
        KOREAN_FONT = 'Malgun'
    else:
        KOREAN_FONT = 'Helvetica'
except Exception:
    KOREAN_FONT = 'Helvetica'

def clean_text_for_pdf(text):
    if not text:
        return ""
    text = text.replace('**', '')
    text = text.replace('<br>', '<br/>').replace('<BR>', '<br/>').replace('<br />', '<br/>')
    return text

# --- 빨간색 이름 도장 생성 함수 ---
def create_name_stamp(name):
    d = Drawing(35, 35)
    d.add(Circle(17.5, 17.5, 15, strokeColor=colors.HexColor("#DC2626"), fillColor=colors.white, strokeWidth=1.2))
    d.add(String(17.5, 13, name, textAnchor='middle', fontName=KOREAN_FONT, fontSize=8.5, fillColor=colors.HexColor("#DC2626")))
    return d

# --- 1. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="스마트 현장 TBM 자동화 시스템", page_icon="🛡️", layout="centered")

st.markdown("""
    <style>
    .main-header { font-size: 22px; font-weight: bold; color: #1E3A8A; text-align: center; margin-bottom: 5px; }
    .sub-desc { font-size: 13px; color: #475569; text-align: center; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🛡️ 스마트 현장 TBM 및 위험성평가 자동화</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-desc">작업 내용을 입력하면 AI가 위험성평가를 수행하고, PDF 생성 및 지정 메일함으로 자동 발송됩니다.</div>', unsafe_allow_html=True)

# --- 2. 사이드바 (설정) ---
with st.sidebar:
    st.header("⚙️ 시스템 설정")

    # 여기서 st.secrets로 API 키를 자동으로 불러옵니다
    try:
        active_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔒 사내 테스트용 API 키 자동 적용됨")
    except:
        active_key = ""
        st.error("⚠️ Streamlit Secrets 설정이 안 되어 있습니다!")

    st.markdown("---")
    st.info(f"📬 **메일 자동 수신처**\n\n모든 TBM 보고서는 아래 주소로 자동 발송됩니다:\n`{FIXED_RECEIVER_EMAIL}`")

# --- 3. 메인 입력 영역 ---
st.markdown("### 📝 현장 TBM 정보 입력")

site_name = st.text_input("🏢 현장명 입력", placeholder="예: 에이엔티 테스트 타워 설치")

col1, col2 = st.columns(2)
with col1:
    tbm_date = st.date_input("📅 작업 날짜 선택", value=datetime.date.today())
with col2:
    worker_count = st.number_input("참여 인원 (명)", min_value=1, max_value=15, value=3)

st.markdown("---")
st.markdown("👥 **참여 작업자 성명 입력** (빈칸에 이름을 바로 입력하세요)")

worker_names = []
cols_input = st.columns(min(int(worker_count), 3))
for i in range(int(worker_count)):
    col_idx = i % 3
    with cols_input[col_idx]:
        w_name = st.text_input(f"작업자 {i+1} 성명", value="", placeholder=f"작업자 {i+1} 이름", key=f"worker_name_{i}")
        if not w_name.strip():
            w_name = f"작업자{i+1}"
        worker_names.append(w_name)

st.markdown("---")
st.markdown("📍 **현장 위치 및 날씨 자동 가져오기 (GPS 연동)**")
st.write("스마트폰에서 아래 버튼을 누르고 **'위치 권한 허용'**을 누르면 현재 계신 곳의 주소와 날씨가 자동으로 채워집니다.")

# 브라우저 GPS 가져오기 컴포넌트 실행
loc_data = streamlit_geolocation()

auto_location = ""
auto_weather = ""

if loc_data and loc_data.get('latitude') and loc_data.get('longitude'):
    lat = loc_data.get('latitude')
    lon = loc_data.get('longitude')

    # 1. 위경도를 한국어 주소로 변환 (OpenStreetMap Nominatim 무료 API)
    try:
        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {'User-Agent': 'SmartTBMApp/1.0'}
        res = requests.get(geo_url, headers=headers, timeout=3).json()
        address = res.get('display_name', '')
        if address:
            parts = address.split(', ')
            if len(parts) >= 4:
                auto_location = f"{parts[-3]} {parts[-4]} {parts[-5]}" if len(parts)>=5 else address
            else:
                auto_location = address
        else:
            auto_location = f"위도: {lat:.4f}, 경도: {lon:.4f}"
    except:
        auto_location = f"위도: {lat:.4f}, 경도: {lon:.4f}"

    # 2. Open-Meteo를 통해 실시간 기온 조회
    try:
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = requests.get(weather_url, timeout=3).json()
        temp = w_res.get("current_weather", {}).get("temperature", "20")
        auto_weather = f"기온 {temp}°C (야외 작업 양호)"
    except:
        auto_weather = "기온 20°C (야외 작업 양호)"

location = st.text_input("📍 작업 위치", value=auto_location, placeholder="예: (위 버튼을 누르면 자동 입력됨)")
weather_info = st.text_input("⛅ 현장 날씨", value=auto_weather, placeholder="예: 기온 22°C (GPS 연동 시 자동 입력됨)")

work_content = st.text_area("🔧 작업 내용 입력", placeholder="예: 엘리베이터 기계실 부품 양중", height=100)

# --- 사진 첨부 방식 선택 ---
st.markdown("---")
st.markdown("📸 **현장 활동 사진 첨부**")
upload_mode = st.radio("첨부 방식을 선택하세요:", ["📁 파일 / 앨범에서 선택", "📷 카메라로 직접 촬영"], horizontal=True)

uploaded_file = None
if upload_mode == "📁 파일 / 앨범에서 선택":
    uploaded_file = st.file_uploader("이미지 파일 업로드", type=["jpg", "jpeg", "png"])
else:
    uploaded_file = st.camera_input("카메라로 현장 촬영하기")

submitted = st.button("🚀 TBM 위험성평가 생성 및 메일 자동 발송", type="primary", use_container_width=True)

# --- 4. 제출 처리 로직 ---
if submitted:
    if not active_key:
        st.error("⚠️ 스트림릿 Secrets에 Gemini API Key가 설정되지 않았습니다!")
    elif not site_name:
        st.error("⚠️ 현장명을 입력해주세요!")
    elif not work_content:
        st.error("⚠️ 작업 내용을 입력해주세요!")
    else:
        with st.spinner("🤖 AI가 현장 작업 내용을 분석하여 위험성평가를 작성 중입니다..."):
            try:
                genai.configure(api_key=active_key)
                model = genai.GenerativeModel('gemini-3.6-flash')

                prompt = f"""
                너는 베테랑 건설/제조업 안전관리 전문가야. 다음 작업 내용에 대해 산업안전보건기준에 맞추어 위험성평가를 수행해줘.
                작업 내용: {work_content}

                반드시 정확히 3개의 위험요인을 도출하고, 오직 마크다운 표(Table) 형태로만 출력해줘. 다른 인사말이나 설명은 절대 적지 마.
                표의 헤더는 정확히 이 순서로 해줘:
                | 번호 | 위험요인 | 잠재 위험성 (재해형태) | 감소 대책 (안전조치) |
                """
                response = model.generate_content(prompt)
                ai_result_text = response.text
            except Exception as e:
                st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
                st.stop()

        st.success("✨ AI 위험성평가 및 현장 데이터 수집 완료!")

        # --- 5. 웹 화면 실시간 결과 미리보기 ---
        st.markdown("---")
        st.subheader("📊 [실시간 화면 미리보기] AI 위험성평가 결과")

        web_table_rows = []
        for line in ai_result_text.split('\n'):
            if '|' in line and '---' not in line:
                cols = [c.replace('**', '').strip() for c in line.split('|')[1:-1]]
                if len(cols) >= 4:
                    web_table_rows.append(cols)

        if len(web_table_rows) > 0:
            st.table(web_table_rows[1:])
        else:
            st.text(ai_result_text)

        # --- 6. PDF 서류 자동 생성 로직 ---
        st.info("📄 공식 TBM 문서 정밀 생성 및 작업자 도장 날인 중입니다...")

        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []

        style_normal = ParagraphStyle('NormalKorean', fontName=KOREAN_FONT, fontSize=9, leading=14, textColor=colors.HexColor("#334155"))
        style_header = ParagraphStyle('HeaderKorean', fontName=KOREAN_FONT, fontSize=9, leading=14, textColor=colors.white)

        title_style = ParagraphStyle(
            'TitleStyle', fontName=KOREAN_FONT, fontSize=16, alignment=1, textColor=colors.HexColor("#1E3A8A"), spaceAfter=15
        )
        h2_style = ParagraphStyle(
            'H2Style', fontName=KOREAN_FONT, fontSize=12, textColor=colors.HexColor("#1E3A8A"), spaceBefore=10, spaceAfter=8
        )

        story.append(Paragraph(f"TBM (Tool Box Meeting) 및 위험성평가 보고서", title_style))
        story.append(Spacer(1, 5))

        meta_data = [
            [Paragraph("<b>현장명</b>", style_normal), Paragraph(site_name, style_normal), Paragraph("<b>작업 일자</b>", style_normal), Paragraph(str(tbm_date), style_normal)],
            [Paragraph("<b>작업 위치</b>", style_normal), Paragraph(location, style_normal), Paragraph("<b>현장 날씨</b>", style_normal), Paragraph(weather_info if weather_info else "정보 없음", style_normal)],
            [Paragraph("<b>참여 인원</b>", style_normal), Paragraph(f"{worker_count}명", style_normal), "", ""],
            [Paragraph("<b>작업 내용</b>", style_normal), Paragraph(work_content, style_normal), "", ""]
        ]
        meta_table = Table(meta_data, colWidths=[70, 190, 75, 190])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('SPAN', (1, 2), (3, 2)),
            ('SPAN', (1, 3), (3, 3)),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("[참여 작업자 서명부]", h2_style))
        story.append(Spacer(1, 4))

        worker_table_rows = [
            [Paragraph("<b>번호</b>", style_header), Paragraph("<b>작업자 성명</b>", style_header), Paragraph("<b>서명 (인)</b>", style_header)]
        ]

        for idx, wname in enumerate(worker_names):
            stamp = create_name_stamp(wname)
            worker_table_rows.append([
                Paragraph(str(idx + 1), style_normal),
                Paragraph(wname, style_normal),
                stamp
            ])

        worker_table = Table(worker_table_rows, colWidths=[50, 250, 234], rowHeights=28)
        worker_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,1), (2,-1), 'CENTER'),
            ('PADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(worker_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("[AI 안전관리 전문가 분석] 위험성평가 결과", h2_style))

        table_rows = []
        table_rows.append([
            Paragraph("<b>번호</b>", style_header),
            Paragraph("<b>위험요인</b>", style_header),
            Paragraph("<b>잠재 위험성</b>", style_header),
            Paragraph("<b>감소 대책</b>", style_header)
        ])

        for line in ai_result_text.split('\n'):
            if '|' in line and '---' not in line:
                cols = [c.strip() for c in line.split('|')[1:-1]]
                if len(cols) >= 4:
                    table_rows.append([
                        Paragraph(clean_text_for_pdf(cols[0]), style_normal),
                        Paragraph(clean_text_for_pdf(cols[1]), style_normal),
                        Paragraph(clean_text_for_pdf(cols[2]), style_normal),
                        Paragraph(clean_text_for_pdf(cols[3]), style_normal)
                    ])

        if len(table_rows) > 1:
            risk_table = Table(table_rows, colWidths=[35, 135, 145, 210])
            risk_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('PADDING', (0,0), (-1,-1), 5),
            ]))
            story.append(risk_table)
        else:
            for line in ai_result_text.split('\n'):
                if line.strip():
                    story.append(Paragraph(clean_text_for_pdf(line), style_normal))

        story.append(Spacer(1, 10))

        if uploaded_file is not None:
            story.append(Paragraph("[현장 활동 사진]", h2_style))
            story.append(Spacer(1, 4))
            try:
                temp_img_path = "temp_uploaded_img.png"
                with open(temp_img_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                img = RLImage(temp_img_path, width=220, height=140)
                story.append(img)
            except Exception as img_err:
                story.append(Paragraph(f"(사진 삽입 생략: {img_err})", style_normal))

        doc.build(story)
        pdf_data = pdf_buffer.getvalue()

        st.download_button(
            label="📥 TBM 평가서 PDF 다운로드",
            data=pdf_data,
            file_name=f"TBM_{site_name}_{tbm_date}.pdf",
            mime="application/pdf"
        )

        # --- 7. Gmail 서버를 통한 자동 이메일 발송 로직 ---
        with st.spinner("📧 Gmail 서버를 통해 안전관리자에게 문서를 전송 중입니다..."):
            try:
                msg = MIMEMultipart()
                msg['From'] = FIXED_SENDER_EMAIL
                msg['To'] = FIXED_RECEIVER_EMAIL
                msg['Subject'] = f"[TBM 보고서] [{site_name}] {tbm_date} 위험성평가 결과"

                body = f"""
                안녕하세요, 안전관리 담당자님.

                [{site_name}] 현장의 {tbm_date} TBM 및 위험성평가 보고서가 자동 접수되었습니다.

                - 현장명: {site_name}
                - 작업 일자: {tbm_date}
                - 작업 위치: {location}
                - 현장 날씨: {weather_info}
                - 참여 인원: {worker_count}명 ({', '.join(worker_names)})
                - 작업 내용: {work_content}

                첨부된 PDF 파일을 확인해 주시기 바랍니다.

                - 스마트 TBM 자동화 시스템 -
                """
                msg.attach(MIMEText(body, 'plain'))

                part = MIMEBase('application', 'octet-stream')
                part.set_payload(pdf_data)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename=TBM_Report_{tbm_date}.pdf')
                msg.attach(part)

                server = smtplib.SMTP_SSL(FIXED_SMTP_SERVER, FIXED_SMTP_PORT, timeout=10)
                server.login(FIXED_SENDER_EMAIL, FIXED_SENDER_PASSWORD)
                server.sendmail(FIXED_SENDER_EMAIL, FIXED_RECEIVER_EMAIL, msg.as_string())
                server.quit()

                st.success(f"🎉 메일 발송 성공! 지정된 관리자 메일함({FIXED_RECEIVER_EMAIL})으로 안전하게 전송되었습니다.")
            except Exception as mail_err:
                st.error(f"❌ 메일 발송 실패 (네트워크 또는 계정 설정 확인): {mail_err}")
