import streamlit as st
import requests
import datetime
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
import google.generativeai as genai

# ReportLab PDF 생성용 라이브러리
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, String

# ==========================================
# 🛠️ [고정 설정] 발송 및 수신 메일 계정 설정
# ==========================================
FIXED_SMTP_SERVER = "smtp.daum.net"
FIXED_SMTP_PORT = 465
FIXED_SENDER_EMAIL = "your_daum_id@daum.net"        # 👈 발송할 본인의 다음(Daum) 메일 주소
FIXED_SENDER_PASSWORD = "your_daum_password"    # 👈 다음 메일 비밀번호 (또는 앱 비밀번호)
FIXED_RECEIVER_EMAIL = "safety@company.com"     # 👈 보고서를 받을 안전관리자(또는 대표님) 메일 주소

# --- 0. 한글 폰트 강제 등록 (리눅스 서버 / 윈도우 환경 자동 분기) ---
try:
    linux_font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    windows_font_path = 'C:/Windows/Fonts/malgun.ttf'
    
    if os.path.exists(linux_font_path):
        # 스트림릿 클라우드 (리눅스 서버) 환경
        pdfmetrics.registerFont(TTFont('NanumGothic', linux_font_path))
        KOREAN_FONT = 'NanumGothic'
    elif os.path.exists(windows_font_path):
        # 내 데스크톱 (윈도우) 환경
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

# --- 빨간색 이름 도장 생성 함수 (사이즈 축소) ---
def create_name_stamp(name):
    d = Drawing(35, 35)
    d.add(Circle(17.5, 17.5, 15, strokeColor=colors.HexColor("#DC2626"), fillColor=colors.white, strokeWidth=1.2))
    d.add(String(17.5, 13, name, textAnchor='middle', fontName=KOREAN_FONT, fontSize=8.5, fillColor=colors.HexColor("#DC2626")))
    return d

# --- 자동 GPS 위치 및 날씨 정보 조회 ---
def get_auto_location_and_weather():
    lat, lon = 37.5665, 126.9780
    location_str = "대한민국 서울특별시"
    try:
        geo_res = requests.get("https://ipapi.co/json/", timeout=3).json()
        city = geo_res.get("city", "서울")
        region = geo_res.get("region", "")
        country = geo_res.get("country_name", "대한민국")
        location_str = f"{country} {region} {city}".strip()
        lat = geo_res.get("latitude", 37.5665)
        lon = geo_res.get("longitude", 126.9780)
    except:
        pass

    weather_str = "현재 기온 24°C (야외 작업 양호)"
    try:
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = requests.get(weather_url, timeout=3).json()
        temp = w_res.get("current_weather", {}).get("temperature", 24)
        weather_str = f"현재 기온 {temp}°C (야외 작업 양호)"
    except:
        pass

    return location_str, weather_str

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
    
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
        
    user_api_key = st.text_input("Gemini API Key 입력", type="password", value=st.session_state.api_key, help="AI 위험성평가 생성을 위해 필요합니다.")
    if user_api_key:
        st.session_state.api_key = user_api_key

    st.markdown("---")
    st.info(f"📬 **메일 자동 수신처**\n\n모든 TBM 보고서는 아래 주소로 자동 발송됩니다:\n`{FIXED_RECEIVER_EMAIL}`")

# --- 자동 위치/날씨 가져오기 ---
auto_location, auto_weather = get_auto_location_and_weather()

# --- 3. 메인 입력 영역 (실시간 반응형) ---
st.markdown("### 📝 현장 TBM 정보 입력")

site_name = st.text_input("🏢 현장명 입력", placeholder="예: 서울 OO오피스텔 신축공사 현장")

col1, col2 = st.columns(2)
with col1:
    tbm_date = st.date_input("📅 작업 날짜 선택", value=datetime.date.today())
with col2:
    worker_count = st.number_input("참여 인원 (명)", min_value=1, max_value=15, value=3)

st.markdown("---")
st.markdown("👥 **참여 작업자 성명 입력**")

worker_names = []
cols_input = st.columns(min(int(worker_count), 3))
for i in range(int(worker_count)):
    col_idx = i % 3
    with cols_input[col_idx]:
        w_name = st.text_input(f"작업자 {i+1} 성명", value=f"작업자{i+1}", key=f"worker_name_{i}")
        worker_names.append(w_name)

st.markdown("---")
location = st.text_input("📍 작업 위치 (자동 GPS 감지됨)", value=auto_location)
work_content = st.text_area("🔧 작업 내용 입력", placeholder="예: 본관 3층 외벽 비계 해체 및 자재 인양 작업", height=100)

uploaded_file = st.file_uploader("📸 현장 활동 사진 업로드", type=["jpg", "jpeg", "png"])

submitted = st.button("🚀 TBM 위험성평가 생성 및 메일 자동 발송", type="primary", use_container_width=True)

# --- 4. 제출 처리 로직 ---
if submitted:
    active_key = st.session_state.get("api_key", "")
    if not active_key:
        st.error("⚠️ 사이드바에 Gemini API Key를 입력해주세요!")
    elif not site_name:
        st.error("⚠️ 현장명을 입력해주세요!")
    elif not work_content:
        st.error("⚠️ 작업 내용을 입력해주세요!")
    else:
        with st.spinner("🤖 AI가 현장 작업 내용을 분석하여 위험성평가를 작성 중입니다..."):
            try:
                genai.configure(api_key=active_key)
                model = genai.GenerativeModel('gemini-3.6-flash')  # 👈 원래 쓰시던 최신 모델 유지!
                
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
            [Paragraph("<b>작업 위치</b>", style_normal), Paragraph(location, style_normal), Paragraph("<b>참여 인원</b>", style_normal), Paragraph(f"{worker_count}명", style_normal)],
            [Paragraph("<b>현장 날씨</b>", style_normal), Paragraph(auto_weather, style_normal), "", ""],
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

        # --- 7. Daum 메일 서버를 통한 자동 이메일 발송 로직 ---
        with st.spinner("📧 Daum 메일 서버를 통해 안전관리자에게 문서를 전송 중입니다..."):
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

                server = smtplib.SMTP_SSL(FIXED_SMTP_SERVER, FIXED_SMTP_PORT)
                server.login(FIXED_SENDER_EMAIL, FIXED_SENDER_PASSWORD)
                server.sendmail(FIXED_SENDER_EMAIL, FIXED_RECEIVER_EMAIL, msg.as_string())
                server.quit()

                st.success(f"🎉 메일 발송 성공! 지정된 관리자 메일함({FIXED_RECEIVER_EMAIL})으로 안전하게 전송되었습니다.")
            except Exception as mail_err:
                st.error(f"❌ 메일 발송 실패: {mail_err}")
