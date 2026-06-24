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
import io
import base64

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

# --- ESTILIZAÇÃO MINIMALISTA E MODERNA ---
st.markdown(
    """
    <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body, #root { background: #f7f7fb; }
    .stApp { color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; }

    /* Header clean */
    .stApp>div:first-child { background: #ffffff; border-bottom: 1px solid #eef2ff; padding: 18px 0 !important; }

    /* Main content clean */
    .stApp>div:not(:first-child) { background: #f7f7fb; }

    /* Buttons: modern flat */
    .stButton { margin: 6px 4px; }
    .stButton>button {
        width: 100%; padding: 14px 16px !important; border-radius: 10px; font-size: 15px; font-weight: 600;
        background: #7c3aed; color: white; border: none;
        box-shadow: 0 6px 18px rgba(124,58,237,0.12);
        transition: all 0.14s ease;
        cursor: pointer;
    }
    .stButton>button:hover {
        background: #6d28d9;
        transform: translateY(-2px);
    }
    .stButton>button:disabled {
        background: #e6e7f8; color:#8b8fbf; cursor: not-allowed; transform: none;
    }

    /* Input fields clean */
    .stFileUploader label, .stCameraInput label { font-weight: 600; font-size: 13px; color: #6b7280; }

    /* Camera: landscape forced, bounded, responsive */
    .stCamera { max-width: 100%; height: auto; margin: 16px 0; border-radius: 10px; overflow: hidden; }
    .stCamera video { 
        width: 100%; height: auto; max-height: 68vh; object-fit: cover;
        aspect-ratio: 16 / 9;
        display: block;
    }
    .stCamera canvas { 
        width: 100%; height: auto; max-height: 68vh; object-fit: cover;
        aspect-ratio: 16 / 9;
        display: block;
    }

    /* Messages & alerts clean */
    .stSuccess, .stError, .stWarning, .stInfo { border-radius: 10px; font-size: 13px; }
    .stSuccess { background: #ecfdf5; color: #065f46; border: 1px solid #bbf7d0; }
    .stError { background: #fff1f2; color: #9f1239; border: 1px solid #fecaca; }

    /* Spacing */
    .stMarkdown, .stText { line-height: 1.5; }

    /* Responsive */
    @media (max-width: 640px) {
        .stApp { font-size: 13px; }
        .stButton>button { padding: 12px 14px !important; font-size: 14px; }
        .stCamera video, .stCamera canvas { max-height: 56vh; }
    }
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
    """Exibe o resultado da IA de forma limpa e legível."""
    st.write("")  # espaço
    st.divider()
    
    try:
        lines = [l.strip() for l in resultado.splitlines() if l.strip()]
        parsed = {}
        for l in lines:
            m = re.match(r"^(?P<k>[A-Za-zÀ-ÿ0-9 _]+)[:\-]+\s*(?P<v>.+)$", l)
            if m:
                parsed[m.group('k').strip().upper()] = m.group('v').strip()

        if 'GABARITO DA IA' in parsed or 'GABARITO' in parsed:
            gab = parsed.get('GABARITO DA IA', parsed.get('GABARITO'))
            st.markdown(f"### ✓ Gabarito: **{gab}**")

        body = parsed.get('RESUMO') if 'RESUMO' in parsed else '\n'.join(lines)
        st.write(body)

        status = parsed.get('STATUS DO ALUNO', parsed.get('STATUS'))
        if status:
            if 'ACERT' in status.upper():
                st.success(f"Status: {status}")
            elif 'ERR' in status.upper():
                st.error(f"Status: {status}")
            else:
                st.info(f"Status: {status}")
    except Exception:
        st.write(resultado)


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
st.title("Corretor Pro")
st.caption(f"Modo: {modo}")
st.divider()

# --- Controles principais: Upload | Colar | Captura | Câmera (cada um acionado por botão) ---
if 'show_uploader' not in st.session_state:
    st.session_state['show_uploader'] = False
if 'camera_active' not in st.session_state:
    st.session_state['camera_active'] = False
if 'camera_image' not in st.session_state:
    st.session_state['camera_image'] = None

# Grid de botões 2x2 simples e limpo
st.write("")  # espaço pequeno
row1_col1, row1_col2 = st.columns(2, gap="small")
row2_col1, row2_col2 = st.columns(2, gap="small")

# Linha 1
with row1_col1:
    if st.button("Upload", use_container_width=True):
        st.session_state['show_uploader'] = not st.session_state['show_uploader']

with row1_col2:
    if ImageGrab is not None:
        if st.button("Colar", use_container_width=True):
            try:
                _p = ImageGrab.grabclipboard()
                if isinstance(_p, list):
                    _p = None
                if _p is not None:
                    st.session_state['pasted_image'] = _p
                    st.success("Imagem colada.")
                else:
                    st.warning("Nenhuma imagem no clipboard.")
            except Exception as e:
                st.error(f"Erro ao acessar clipboard: {e}")
    else:
        st.button("Colar", disabled=True, use_container_width=True)

# Linha 2
with row2_col1:
    if platform.system() == 'Windows':
        if st.button("🖼️ Captura", use_container_width=True):
            try:
                subprocess.Popen(["explorer.exe", "ms-screenclip:"])
                st.info("Use a Tesourinha para capturar.")
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
                    st.success("Captura realizada.")
                else:
                    st.error("Nenhuma imagem capturada.")
            except Exception as e:
                st.error(f"Erro ao capturar: {e}")
    else:
        st.button("🖼️ Captura", disabled=True, use_container_width=True)

with row2_col2:
    if st.button("Câmera", use_container_width=True):
        st.session_state['open_rear_cam'] = True

st.write("")  # espaço

# Mostrar uploader condicionalmente
uploaded_file = None
if st.session_state['show_uploader']:
    uploaded_file = st.file_uploader("Enviar imagem", type=["jpg", "jpeg", "png"]) 

# Mostrar câmera quando ativada
if st.session_state.get('open_rear_cam', False):
    try:
        from camera_component import camera_component
        data = camera_component(key='rear_cam', height=900)
        if data:
            header, b64 = data.split(',', 1) if ',' in data else (None, data)
            img_bytes = base64.b64decode(b64)
            st.session_state['camera_image'] = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            st.session_state['open_rear_cam'] = False
            run_analysis_on_image(st.session_state['camera_image'])
    except Exception as e:
        st.error("Erro ao abrir o componente de câmera.")
        st.info("Possíveis causas: 'pyarrow' não instalado no ambiente usado pelo Streamlit, ou é necessário reiniciar o servidor Streamlit após instalar dependências.")
        st.markdown("- Se você instalou `pyarrow` agora, pare o servidor e execute `streamlit run app.py` novamente.\n- Verifique permissões de câmera no navegador (permitir câmera, HTTPS).\n- Teste em Chrome/Edge no Android para melhor compatibilidade.)")
        st.exception(e)

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
    st.write("")  # espaço
    st.image(img, use_column_width=True)
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Analisar", use_container_width=True):
            run_analysis_on_image(img)
