import streamlit as st
import google.generativeai as genai
from PIL import Image
try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None
import re
import traceback
import subprocess
import time
import platform

from datetime import datetime

LOG_PATH = "analysis.log"

def log_event(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass

# Configuração da Página
st.set_page_config(page_title="IA Corretor Pro", layout="wide", page_icon="🎓")

# --- ESTILIZAÇÃO RESPONSIVA ---
st.markdown(
    """
    <style>
    :root{
      --bg1: #0b1220;
      --bg2: #071122;
      --card: rgba(255,255,255,0.04);
      --glass: rgba(255,255,255,0.03);
      --accent1: #4cc9f0;
      --accent2: #7b2ff7;
      --muted: #9aa7b2;
    }
    html,body,#root{background:linear-gradient(180deg,var(--bg1) 0%, var(--bg2) 100%);}
    .stApp { color: #e6eef8; font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; }
    .css-1v3fvcr .main, .stApp>div { background: transparent }
    .stSidebar { backdrop-filter: blur(8px); background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border-radius:12px }
    .stButton>button {
        width:100%; border-radius:12px; height:3.2em; background: linear-gradient(90deg,var(--accent1),var(--accent2)); color: #021022; font-weight:700; border: none;
        box-shadow: 0 6px 18px rgba(123,47,247,0.12); transition: transform .12s ease, box-shadow .12s ease;
    }
    .stButton>button:hover{ transform: translateY(-4px); box-shadow: 0 18px 36px rgba(123,47,247,0.14); }
    .result-card{ padding:20px; border-radius:14px; background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border: 1px solid rgba(255,255,255,0.03); box-shadow: 0 8px 30px rgba(2,6,23,0.6); }
    .big-title{font-size:30px; font-weight:700; margin-bottom:6px; color: #eaf6ff}
    .muted{color:var(--muted); font-size:14px}
    .stTextInput>div>input, .stTextArea>div>textarea{background:transparent;color:#e6eef8;border:1px solid rgba(255,255,255,0.03); border-radius:8px;padding:10px}
    @media (max-width:600px){ .stButton>button{height:3.8em; font-size:15px} .result-card{padding:12px} .big-title{font-size:22px} }
    /* Camera fullscreen helper */
    .stCamera { position: fixed !important; inset: 0 0 0 0; width:100vw !important; height:100vh !important; z-index:9999; background: #000; display:flex; align-items:center; justify-content:center }
    .stCamera video { width:100%; height:100%; object-fit:cover }
    </style>
    """,
    unsafe_allow_html=True,
)

# Configuração da API
# Leia a chave de `st.secrets` para evitar comitar credenciais no repositório.
API_KEY = None
try:
    API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    API_KEY = None

if not API_KEY:
    import os
    API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    st.warning("A chave da API do Gemini não está configurada. Configure `GEMINI_API_KEY` em Secrets no Streamlit Cloud ou como variável de ambiente.")
else:
    genai.configure(api_key=API_KEY)

# Modelo a usar (pode ser alterado na sidebar)
DEFAULT_MODEL = "models/gemini-2.5-flash"

def call_gemini_vision(image, prompt):
    # Instrumentação para depuração: logs no terminal
    try:
        print("call_gemini_vision: iniciando chamada ao Gemini")
        # Não logar a chave completa por segurança
        print(f"API key presente: {bool(API_KEY) and API_KEY != 'SUA_CHAVE_AQUI'}")
        print(f"Usando modelo: {MODEL_TO_USE}")
        model = genai.GenerativeModel(MODEL_TO_USE)
        # A API pode aceitar imagem/bytes; estamos passando o objeto PIL — a biblioteca deve suportar
        response = model.generate_content([prompt, image])
        print("call_gemini_vision: resposta recebida")
        return response.text
    except Exception as e:
        err_str = str(e)
        print("call_gemini_vision: erro ao chamar Gemini:", err_str)
        # Se for erro de modelo não encontrado, tente listar modelos disponíveis
        # Detect billing / prepay depletion (429)
        if 'prepayment credits are depleted' in err_str.lower() or '429' in err_str:
            msg = (
                "Seu projeto ficou sem créditos/prepagamento para o Gemini (erro 429). "
                "Acesse https://ai.studio/projects para gerenciar seu projeto e faturamento."
            )
            log_event(f"Billing error detected: {err_str}")
            raise Exception(msg)

        try:
            if 'not found' in err_str.lower() or 'notfound' in err_str.lower() or '404' in err_str:
                try:
                    models = genai.list_models()
                    model_names = [m.name if hasattr(m, 'name') else str(m) for m in models]
                    msg = (
                        f"Modelo '{MODEL_TO_USE}' não encontrado. Modelos disponíveis (exemplos): {model_names[:10]}"
                    )
                    log_event(msg)
                    raise Exception(msg)
                except Exception as le:
                    log_event(f"Erro ao listar modelos: {le}")
                    raise
        except Exception:
            pass
        raise


def display_result_formatted(resultado: str):
    """Exibe o resultado da IA de forma mais legível e colorida."""
    try:
        # Tentar parsear linhas chave: value
        lines = [l.strip() for l in resultado.splitlines() if l.strip()]
        parsed = {}
        for l in lines:
            m = re.match(r"^(?P<k>[A-Za-zÀ-ÿ0-9 _]+)[:\-]+\s*(?P<v>.+)$", l)
            if m:
                parsed[m.group('k').strip().upper()] = m.group('v').strip()

        # Exibição elegante
        if 'GABARITO DA IA' in parsed or 'GABARITO' in parsed:
            gab = parsed.get('GABARITO DA IA', parsed.get('GABARITO'))
            st.markdown(f"**Gabarito (IA):** <span style='color:#0a7f00; font-weight:700'>{gab}</span>", unsafe_allow_html=True)

        if 'RESUMO' in parsed:
            resumo = parsed['RESUMO']
            st.markdown(f"<div style='background:#fff8e1;padding:10px;border-radius:6px'>{resumo}</div>", unsafe_allow_html=True)
        else:
            # tenta juntar outras linhas como corpo
            body = '\n'.join(lines)
            st.markdown(f"<div style='background:#f6f8fa;padding:10px;border-radius:6px;white-space:pre-wrap'>{body}</div>", unsafe_allow_html=True)

        status = parsed.get('STATUS DO ALUNO', parsed.get('STATUS'))
        if status:
            if 'ACERT' in status.upper():
                st.success(f"Status do aluno: {status}")
            elif 'ERR' in status.upper():
                st.error(f"Status do aluno: {status}")
            else:
                st.info(f"Status do aluno: {status}")
    except Exception:
        st.text(resultado)


def run_analysis_on_image(img):
    """Roda o fluxo de análise sobre uma imagem PIL e exibe o resultado."""
    if img is None:
        st.warning("Nenhuma imagem para analisar.")
        return

    with st.spinner("IA processando..."):
        try:
            log_event("analysis button clicked")

            if modo == "IA Resolve (Bancas/Concursos)":
                prompt = """
                Você é um professor especialista em concursos públicos. 
                Analise a imagem da questão enviada:
                1. Identifique o enunciado e as alternativas.
                2. Resolva a questão passo a passo.
                3. Indique claramente qual é a ALTERNATIVA CORRETA.
                4. Se houver algo marcado pelo aluno (ex: um círculo ou X), identifique se ele acertou ou errou.
                Retorne no formato:
                GABARITO DA IA: [Letra]
                RESUMO: [Breve explicação do porquê]
                STATUS DO ALUNO: [Acertou/Errou/Não identificado]
                """
            else:
                prompt = f"""
                Esta imagem contém respostas de um aluno. 
                Extraia as alternativas marcadas para as questões. 
                Gabarito esperado: {gabarito_oficial}
                Retorne uma lista formatada de cada questão e se o aluno acertou baseado no gabarito fornecido.
                """

            if debug_mode:
                resultado = "GABARITO DA IA: A\nRESUMO: Resposta simulada em modo de depuração.\nSTATUS DO ALUNO: Não identificado"
            else:
                log_event("calling call_gemini_vision")
                resultado = call_gemini_vision(img, prompt)
                log_event("call_gemini_vision returned")

        except Exception as e:
            tb = traceback.format_exc()
            log_event(f"call_gemini_vision error: {e}")
            st.error("Erro ao chamar a API do Gemini — verifique a chave e a conexão.")
            st.code(tb)
            return

    # Exibir resultado formatado
    if resultado:
        display_result_formatted(resultado)
    else:
        st.info("Nenhum resultado retornado pela análise.")

# --- INTERFACE LATERAL ---
st.sidebar.title("Modo de Operação")
modo = st.sidebar.radio("Selecione como corrigir:", 
                         ["IA Resolve (Bancas/Concursos)", "Gabarito Prévio (Manual)"])

# Debug: modo que não chama a API (retorna resposta simulada)
debug_mode = st.sidebar.checkbox("Modo Depuração (usar resposta simulada)", value=False)

# Permite ao usuário definir qual modelo usar
MODEL_TO_USE = st.sidebar.text_input("Modelo (ex: gemini-2.5-flash or models/gemini-2.5-flash)", value=DEFAULT_MODEL)
# Normaliza o nome: garante prefixo 'models/' se o usuário não colocar
if MODEL_TO_USE and not MODEL_TO_USE.startswith("models/"):
    MODEL_TO_USE = "models/" + MODEL_TO_USE

gabarito_oficial = {}

if modo == "Gabarito Prévio (Manual)":
    st.sidebar.subheader("Configurar Gabarito")
    num_questoes = st.sidebar.number_input("Total de questões", 1, 50, 5)
    cols = st.sidebar.columns(2)
    for i in range(1, num_questoes + 1):
        with cols[(i-1)%2]:
            gabarito_oficial[str(i)] = st.selectbox(f"Q{i}", ["A", "B", "C", "D", "E"], key=f"gab_{i}")

# --- ÁREA PRINCIPAL ---
st.title("Corretor Pro — Correção Automatizada")
st.write(f"Modo Atual: **{modo}**")

# --- Controles principais: Upload | Colar | Captura | Câmera (cada um acionado por botão) ---
if 'show_uploader' not in st.session_state:
    st.session_state['show_uploader'] = False
if 'camera_active' not in st.session_state:
    st.session_state['camera_active'] = False
if 'camera_image' not in st.session_state:
    st.session_state['camera_image'] = None

cols = st.columns([1,1,1,1])
with cols[0]:
    if st.button("Upload"):
        st.session_state['show_uploader'] = not st.session_state['show_uploader']
with cols[1]:
    if ImageGrab is not None:
        if st.button("Colar"):
            try:
                _p = ImageGrab.grabclipboard()
                if isinstance(_p, list):
                    _p = None
                if _p is not None:
                    st.session_state['pasted_image'] = _p
                    st.success("Imagem colada no clipboard.")
                else:
                    st.warning("Nenhuma imagem válida no clipboard.")
            except Exception as e:
                st.error(f"Erro ao acessar clipboard: {e}")
    else:
        st.button("Colar", disabled=True)
with cols[2]:
    # Captura de tela (Windows Tesourinha)
    if platform.system() == 'Windows':
        if st.button("Captura de tela"):
            try:
                subprocess.Popen(["explorer.exe", "ms-screenclip:"])
                st.info("Abra a Tesourinha e selecione a área. Aguardando imagem no clipboard...")
                grabbed = None
                for _ in range(20):
                    time.sleep(0.3)
                    try:
                        _g = ImageGrab.grabclipboard()
                        if _g and not isinstance(_g, list):
                            grabbed = _g
                            break
                    except Exception:
                        pass

                if grabbed is not None:
                    st.session_state['pasted_image'] = grabbed
                    st.success("Captura salva no clipboard e carregada no app.")
                else:
                    st.error("Nenhuma imagem encontrada no clipboard. Certifique-se de completar a captura na Tesourinha.")
            except Exception as e:
                st.error(f"Erro ao abrir Tesourinha ou capturar: {e}")
    else:
        st.button("Captura de tela", disabled=True)
with cols[3]:
    if st.button("Câmera"):
        st.session_state['camera_active'] = not st.session_state['camera_active']

# Mostrar uploader condicionalmente quando usuário clicar em Upload
uploaded_file = None
if st.session_state['show_uploader']:
    uploaded_file = st.file_uploader("Enviar imagem da prova", type=["jpg", "jpeg", "png"]) 

# Mostrar câmera quando ativada
if st.session_state['camera_active']:
    # Make camera area occupy most of the viewport on mobile by adding CSS
    st.markdown(
        """
        <style>
        .stCamera { position: fixed !important; inset: 0 0 0 0; width:100vw !important; height:100vh !important; z-index:9999; background: #000; display:flex; align-items:center; justify-content:center }
        .stCamera video { width:100%; height:100%; object-fit:cover }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cam = st.camera_input("Capturar foto da prova")
    if cam is not None:
        try:
            st.session_state['camera_image'] = Image.open(cam)
            st.success("Foto capturada e carregada.")
            # close camera UI
            st.session_state['camera_active'] = False
            # automaticamente iniciar análise após captura
            run_analysis_on_image(st.session_state['camera_image'])
        except Exception as e:
            st.error(f"Erro ao processar imagem da câmera: {e}")

# Prioriza upload do usuário; se não houver, usa câmera capturada ou imagem colada (persistida em session_state)
img = None
pasted = st.session_state.get('pasted_image') if 'pasted_image' in st.session_state else None
camera_img = st.session_state.get('camera_image') if 'camera_image' in st.session_state else None
if uploaded_file is not None:
    try:
        img = Image.open(uploaded_file)
    except Exception as e:
        st.error(f"Erro ao abrir arquivo enviado: {e}")
elif camera_img is not None:
    img = camera_img
elif pasted is not None:
    img = pasted

if img is not None:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.image(img, caption="Imagem Carregada", width=400)

    with col2:
        if st.button("Analisar e corrigir"):
            run_analysis_on_image(img)