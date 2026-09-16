import streamlit as st
import datetime
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from email import encoders
from io import BytesIO
import requests
import google.generativeai as genai
from streamlit_geolocation import streamlit_geolocation
from PIL import Image as PilImage

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, String

st.set_page_config(page_title="TBM Studio", page_icon="✦", layout="centered", initial_sidebar_state="expanded")

try:
    if os.path.exists('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'):
        pdfmetrics.registerFont(TTFont('NanumGothic', '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'))
        KOREAN_FONT = 'NanumGothic'
    elif os.path.exists('C:/Windows/Fonts/malgun.ttf'):
        pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
        KOREAN_FONT = 'Malgun'
    else:
        KOREAN_FONT = 'Helvetica'
except Exception:
    KOREAN_FONT = 'Helvetica'

def clean_text_for_pdf(text):
    return (text or '').replace('**', '').replace('<br>', '<br/>').replace('<BR>', '<br/>').replace('<br />', '<br/>')

def create_name_stamp(name):
    stamp = Drawing(35, 35)
    stamp.add(Circle(17.5, 17.5, 15, strokeColor=colors.HexColor('#0E7490'), fillColor=colors.white, strokeWidth=1.2))
    stamp.add(String(17.5, 13, name, textAnchor='middle', fontName=KOREAN_FONT, fontSize=8.5, fillColor=colors.HexColor('#0E7490')))
    return stamp

# Sensitive values belong in Streamlit Secrets, never in source control.
def secret(name, default=''):
    return st.secrets[name] if name in st.secrets else default

GEMINI_API_KEY = secret('GEMINI_API_KEY')
SMTP_SERVER = secret('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(secret('SMTP_PORT', 465))
SENDER_EMAIL = secret('SENDER_EMAIL')
SENDER_PASSWORD = secret('SENDER_PASSWORD')
RECEIVER_EMAIL = secret('RECEIVER_EMAIL')

st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
:root { --ink:#f7f8fa; --muted:#9ba4b7; --panel:#151923; --line:rgba(255,255,255,.10); --aqua:#61f6dc; --blue:#5a8cff; }
.stApp { background: radial-gradient(circle at 7% -4%, #24375c 0, transparent 28rem), radial-gradient(circle at 96% 4%, #143b39 0, transparent 25rem), #0d1017; color:var(--ink); }
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:900px; padding-top:2.5rem; padding-bottom:4rem; }
html, body, [class*="css"], .stMarkdown { font-family:'Noto Sans KR', sans-serif; }
.hero { position:relative; overflow:hidden; padding:2.2rem 2.2rem 1.9rem; border:1px solid var(--line); border-radius:24px; background:linear-gradient(130deg,rgba(30,40,62,.9),rgba(17,22,31,.9)); box-shadow:0 18px 60px rgba(0,0,0,.28), inset 0 1px rgba(255,255,255,.07); margin-bottom:1.5rem; }
.hero:after { content:''; position:absolute; width:220px; height:220px; right:-75px; top:-120px; border-radius:50%; background:rgba(97,246,220,.14); filter:blur(18px); }
.eyebrow { color:var(--aqua); font:500 11px 'DM Mono', monospace; letter-spacing:.16em; }
.hero h1 { font-size:30px; line-height:1.25; letter-spacing:-.045em; margin:.45rem 0 .55rem; color:#fff; }
.hero p { max-width:620px; color:var(--muted); font-size:14px; margin:0; line-height:1.7; }
.section-label { color:#fff; font-size:18px; font-weight:700; letter-spacing:-.03em; margin:2rem 0 .8rem; }
.section-label span { color:var(--aqua); margin-right:.35rem; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#111722,#0d1017); border-right:1px solid var(--line); }
[data-testid="stSidebar"] h2 { font-size:18px; }
.stTextInput input, .stTextArea textarea, [data-baseweb="input"] input { background:rgba(255,255,255,.045)!important; color:#f8fafc!important; border:1px solid var(--line)!important; border-radius:12px!important; }
.stTextInput input:focus, .stTextArea textarea:focus { border-color:var(--aqua)!important; box-shadow:0 0 0 3px rgba(97,246,220,.11)!important; }
label, .stMarkdown p { color:#dbe1eb; }
[data-testid="stNumberInput"] button, [data-testid="stDateInput"] button { background:#212938!important; color:var(--aqua)!important; border-color:var(--line)!important; }
.stRadio [role="radiogroup"] { gap:8px; }
.stRadio label { background:rgba(255,255,255,.04); border:1px solid var(--line); border-radius:999px; padding:.35rem .65rem; }
[data-testid="stFileUploader"] { border:1px dashed rgba(97,246,220,.42); border-radius:16px; background:rgba(97,246,220,.035); }
.stButton > button { min-height:52px; border:0!important; border-radius:14px!important; color:#071817!important; font-weight:800!important; background:linear-gradient(100deg,#61f6dc,#76d8ff)!important; box-shadow:0 10px 28px rgba(97,246,220,.20); transition:transform .18s ease, box-shadow .18s ease; }
.stButton > button:hover { transform:translateY(-2px); box-shadow:0 14px 34px rgba(97,246,220,.34); }
[data-testid="stAlert"] { border-radius:13px; }
hr { border-color:var(--line)!important; margin:1.6rem 0!important; }
.footer { text-align:center; color:#6f7a8d; font:11px 'DM Mono', monospace; letter-spacing:.08em; margin-top:2.6rem; }
</style>
<section class="hero"><div class="eyebrow">SAFETY INTELLIGENCE / TBM STUDIO</div><h1>현장 안전을 더 선명하게,<br>보고는 더 매끄럽게.</h1><p>작업 정보를 입력하면 AI가 위험성평가를 정리하고, 공식 보고서를 PDF와 메일로 즉시 전달합니다.</p></section>
''', unsafe_allow_html=True)

with st.sidebar:
    st.markdown('## ✦ TBM Studio')
    st.caption('SMART SITE SAFETY SYSTEM')
    st.divider()
    st.markdown('#### 시스템 연결')
    if GEMINI_API_KEY:
        st.success('AI 분석 엔진이 연결되었습니다.')
    else:
        st.warning('GEMINI_API_KEY를 Secrets에 설정해주세요.')
    st.markdown('#### 보고서 수신처')
    st.info(f'`{RECEIVER_EMAIL or "RECEIVER_EMAIL 미설정"}`')
    st.caption('수신처는 Streamlit Secrets에서 안전하게 관리됩니다.')

st.markdown('<div class="section-label"><span>01</span> 현장 정보</div>', unsafe_allow_html=True)
site_name = st.text_input('현장명', placeholder='예: 에이엔티 테스트 타워 설치')
col1, col2 = st.columns(2)
with col1: tbm_date = st.date_input('작업 날짜', value=datetime.date.today())
with col2: worker_count = st.number_input('참여 인원', min_value=1, max_value=15, value=3)

st.markdown('<div class="section-label"><span>02</span> 참여 작업자</div>', unsafe_allow_html=True)
worker_names = []
for row_start in range(0, int(worker_count), 3):
    for col_idx, col in enumerate(st.columns(3)):
        index = row_start + col_idx
        if index < int(worker_count):
            with col:
                name = st.text_input(f'작업자 {index + 1}', placeholder='성명', key=f'worker_{index}')
                worker_names.append(name.strip() or f'작업자{index + 1}')

st.markdown('<div class="section-label"><span>03</span> 작업 환경</div>', unsafe_allow_html=True)
with st.expander('📍 GPS로 현재 위치와 날씨 불러오기', expanded=False):
    loc_data = streamlit_geolocation()
auto_location, auto_weather = '', ''
if 'loc_data' in locals() and loc_data and loc_data.get('latitude') and loc_data.get('longitude'):
    lat, lon = loc_data['latitude'], loc_data['longitude']
    try:
        response = requests.get(f'https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18', headers={'User-Agent':'TBMStudio/1.0'}, timeout=3).json()
        auto_location = response.get('display_name', f'위도 {lat:.4f}, 경도 {lon:.4f}')
    except Exception: auto_location = f'위도 {lat:.4f}, 경도 {lon:.4f}'
    try:
        temperature = requests.get(f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true', timeout=3).json()['current_weather']['temperature']
        auto_weather = f'기온 {temperature}°C'
    except Exception: auto_weather = '날씨 정보 확인 필요'
location = st.text_input('작업 위치', value=auto_location, placeholder='예: 엘리베이터 기계실')
weather_info = st.text_input('현장 날씨', value=auto_weather, placeholder='예: 기온 22°C, 맑음')
work_content = st.text_area('작업 내용', placeholder='예: 엘리베이터 기계실 부품 양중', height=115)

st.markdown('<div class="section-label"><span>04</span> 현장 기록</div>', unsafe_allow_html=True)
upload_mode = st.radio('사진 첨부 방식', ['파일 / 앨범에서 선택', '카메라로 촬영'], horizontal=True, label_visibility='collapsed')
uploaded_files = st.file_uploader('현장 사진', type=['jpg','jpeg','png'], accept_multiple_files=True) if upload_mode == '파일 / 앨범에서 선택' else [f for f in [st.camera_input('현장 촬영')] if f]

submitted = st.button('✦ 위험성평가 생성 및 보고서 발송', type='primary', use_container_width=True)

if submitted:
    if not GEMINI_API_KEY or not SENDER_EMAIL or not SENDER_PASSWORD or not RECEIVER_EMAIL:
        st.error('Secrets에 Gemini 및 메일 설정을 완료해주세요.')
    elif not site_name or not work_content:
        st.error('현장명과 작업 내용을 입력해주세요.')
    else:
        with st.spinner('AI가 현장 작업을 분석하고 있습니다…'):
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                prompt = f'''너는 건설/제조업 안전관리 전문가다. 작업 내용: {work_content}\n정확히 3개의 위험요인을 도출하고, 아래 헤더를 사용한 마크다운 표만 출력하라.\n| 번호 | 위험요인 | 잠재 위험성 (재해형태) | 감소 대책 (안전조치) |'''
                ai_result_text = genai.GenerativeModel('gemini-3.5-flash-lite').generate_content(prompt).text
            except Exception as error:
                st.error(f'AI 분석 오류: {error}'); st.stop()
        st.success('위험성평가가 완성되었습니다.')
        st.markdown('<div class="section-label"><span>RESULT</span> AI 위험성평가</div>', unsafe_allow_html=True)
        st.markdown(ai_result_text)

        pdf_buffer, story = BytesIO(), []
        normal = ParagraphStyle('normal', fontName=KOREAN_FONT, fontSize=9, leading=14, textColor=colors.HexColor('#25334A'))
        header = ParagraphStyle('header', fontName=KOREAN_FONT, fontSize=9, leading=14, textColor=colors.white)
        title = ParagraphStyle('title', fontName=KOREAN_FONT, fontSize=16, alignment=1, textColor=colors.HexColor('#0E7490'), spaceAfter=15)
        h2 = ParagraphStyle('h2', fontName=KOREAN_FONT, fontSize=12, textColor=colors.HexColor('#0E7490'), spaceBefore=10, spaceAfter=8)
        story += [Paragraph('TBM (Tool Box Meeting) 및 위험성평가 보고서', title), Spacer(1, 5)]
        meta = [[Paragraph('<b>현장명</b>',normal),Paragraph(site_name,normal),Paragraph('<b>작업 일자</b>',normal),Paragraph(str(tbm_date),normal)], [Paragraph('<b>작업 위치</b>',normal),Paragraph(location,normal),Paragraph('<b>현장 날씨</b>',normal),Paragraph(weather_info or '정보 없음',normal)], [Paragraph('<b>참여 인원</b>',normal),Paragraph(f'{worker_count}명',normal),'',''], [Paragraph('<b>작업 내용</b>',normal),Paragraph(work_content,normal),'','']]
        table = Table(meta, colWidths=[70,190,75,190]); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F0FDFA')),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#B6D9D5')),('SPAN',(1,2),(3,2)),('SPAN',(1,3),(3,3)),('PADDING',(0,0),(-1,-1),5)])); story += [table, Spacer(1,10)]
        story += [Paragraph('[참여 작업자 서명부]',h2)]
        workers = [[Paragraph('<b>번호</b>',header),Paragraph('<b>작업자 성명</b>',header),Paragraph('<b>서명 (인)</b>',header)]] + [[Paragraph(str(i+1),normal),Paragraph(n,normal),create_name_stamp(n)] for i,n in enumerate(worker_names)]
        table = Table(workers,colWidths=[50,250,234],rowHeights=28); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0E7490')),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#B6D9D5')),('ALIGN',(2,1),(2,-1),'CENTER')])); story += [table,Spacer(1,10),Paragraph('[AI 안전관리 전문가 분석] 위험성평가 결과',h2)]
        rows = [[Paragraph(f'<b>{x}</b>',header) for x in ['번호','위험요인','잠재 위험성','감소 대책']]]
        for line in ai_result_text.splitlines():
            cells = [c.strip() for c in line.split('|')[1:-1]] if '|' in line and '---' not in line else []
            if len(cells) >= 4 and cells[0] != '번호': rows.append([Paragraph(clean_text_for_pdf(x),normal) for x in cells[:4]])
        if len(rows)>1:
            table=Table(rows,colWidths=[35,135,145,210]); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0E7490')),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#B6D9D5')),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),5)])); story.append(table)
        for i, file in enumerate(uploaded_files):
            try:
                image = PilImage.open(file); image.thumbnail((800,800)); image.convert('RGB').save(f'temp_{i}.jpg','JPEG',quality=80); story += [Spacer(1,8),RLImage(f'temp_{i}.jpg',width=220,height=140)]
            except Exception: pass
        SimpleDocTemplate(pdf_buffer,pagesize=A4,rightMargin=30,leftMargin=30,topMargin=30,bottomMargin=30).build(story)
        pdf_data=pdf_buffer.getvalue()
        st.download_button('PDF 보고서 다운로드',pdf_data,f'TBM_{site_name}_{tbm_date}.pdf','application/pdf',use_container_width=True)
        with st.spinner('안전관리자에게 보고서를 전송하고 있습니다…'):
            try:
                msg=MIMEMultipart(); msg['From']=SENDER_EMAIL; msg['To']=RECEIVER_EMAIL; msg['Subject']=f'[TBM 보고서] {site_name} | {tbm_date}'
                msg.attach(MIMEText(f'{site_name} 현장의 TBM 및 위험성평가 보고서입니다.\\n\\n작업 내용: {work_content}','plain'))
                part=MIMEBase('application','octet-stream'); part.set_payload(pdf_data); encoders.encode_base64(part); part.add_header('Content-Disposition','attachment',filename=Header(f'TBM_{site_name}_{tbm_date}.pdf','utf-8').encode()); msg.attach(part)
                server=smtplib.SMTP_SSL(SMTP_SERVER,SMTP_PORT,timeout=10); server.login(SENDER_EMAIL,SENDER_PASSWORD); server.sendmail(SENDER_EMAIL,RECEIVER_EMAIL,msg.as_string()); server.quit()
                st.success('보고서가 안전관리자 메일함으로 전송되었습니다.')
            except Exception as error: st.error(f'메일 발송 실패: {error}')

st.markdown('<div class="footer">TBM STUDIO · SAFETY, REFINED</div>', unsafe_allow_html=True)
