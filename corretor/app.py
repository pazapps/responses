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
import streamlit.components.v1 as components

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
    :root{--accent:#0066cc;--bg:#071022;--card:#0f1724;--muted:#94a3b8}
    html,body,#root{background:var(--bg)}
    .stApp { color: #e6eef8; font-family: Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; }
    .stButton>button { width:100%; border-radius:10px; height:3.2em; background:var(--accent); color:white; font-weight:600 }
    .result-card{ padding:18px; border-radius:12px; background:var(--card); box-shadow:0 6px 18px rgba(2,6,23,0.6); }
    @media (max-width:600px){ .stButton>button{height:3.8em; font-size:16px} .result-card{padding:14px} }
    .big-title{font-size:28px; font-weight:800; margin-bottom:6px}
    .subtle{color:var(--muted)}
    .stTextInput>div>input, .stTextArea>div>textarea{background:#071022;color:#e6eef8}
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
st.sidebar.title("🎮 Modo de Operação")
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
st.title("🚀 Corretor de Provas Inteligente")
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
    if st.button("📁 Upload"):
        st.session_state['show_uploader'] = not st.session_state['show_uploader']
    with cols[1]:
        if ImageGrab is not None:
            if st.button("📋 Colar"):
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
            # Fallback: provide a browser-based paste catcher using a small HTML/JS component
            if st.button("📋 Colar (Navegador)"):
                paste_component = components.html(
                    """
                    <html>
                    <body style='background:#071022;color:#e6eef8;display:flex;align-items:center;justify-content:center;height:100%;'>
                    <div id="msg" style='text-align:center'>Cole uma imagem aqui (Ctrl+V / Colar)</div>
                    <script src="https://unpkg.com/@streamlit/component-lib@latest/dist/streamlit-component-lib.js"></script>
                    <script>
                      const msg = document.getElementById('msg');
                      window.addEventListener('paste', async (e) => {
                        const items = (e.clipboardData || e.originalEvent.clipboardData).items;
                        for (const item of items) {
                          if (item.type.indexOf('image') !== -1) {
                            const blob = item.getAsFile();
                            const reader = new FileReader();
                            reader.onload = () => {
                              const dataUrl = reader.result;
                              Streamlit.setComponentValue(dataUrl);
                            };
                            reader.readAsDataURL(blob);
                            return;
                          }
                        }
                        Streamlit.setComponentValue(null);
                      });
                      window.focus();
                    </script>
                    </body>
                    </html>
                    """,
                    height=220,
                )
                if paste_component:
                    try:
                        header, encoded = paste_component.split(',', 1)
                        decoded = base64.b64decode(encoded)
                        pil_img = Image.open(io.BytesIO(decoded)).convert('RGB')
                        st.session_state['pasted_image'] = pil_img
                        st.success('Imagem colada via navegador.')
                    except Exception as e:
                        st.error(f'Erro ao processar imagem colada: {e}')
with cols[2]:
    # Captura de tela (Windows Tesourinha)
    if platform.system() == 'Windows':
        if st.button("🖼️ Capturar"):
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
        st.button("🖼️ Capturar", disabled=True)
with cols[3]:
    if st.button("📷 Câmera"):
        st.session_state['camera_active'] = not st.session_state['camera_active']

# Mostrar uploader condicionalmente quando usuário clicar em Upload
uploaded_file = None
if st.session_state['show_uploader']:
    uploaded_file = st.file_uploader("Envie a imagem da questão ou da prova", type=["jpg", "jpeg", "png"]) 

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
    cam = st.camera_input("Tire uma foto da prova (use a câmera do dispositivo)")
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
        st.session_state['uploaded_image'] = img
        st.success("Arquivo enviado e carregado.")
        # Evita rodar análise repetidas vezes em reruns
        if not st.session_state.get('uploaded_processed', False):
            st.session_state['uploaded_processed'] = True
            run_analysis_on_image(img)
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
        # Only enable Paste on Windows to avoid platform clipboard tool dependencies on Linux/Android
        if platform.system() == 'Windows' and ImageGrab is not None:
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
                        # For non-Windows, offer the browser paste button here too
                        if st.button("Colar (Navegador)", use_container_width=True):
                                paste_component = components.html(
                                        """
                                        <html>
                                        <body style='background:#071022;color:#e6eef8;display:flex;align-items:center;justify-content:center;height:100%;'>
                                        <div id="msg" style='text-align:center'>Cole uma imagem aqui (Ctrl+V / Colar)</div>
                                        <script src="https://unpkg.com/@streamlit/component-lib@latest/dist/streamlit-component-lib.js"></script>
                                        <script>
                                            const msg = document.getElementById('msg');
                                            window.addEventListener('paste', async (e) => {
                                                const items = (e.clipboardData || e.originalEvent.clipboardData).items;
                                                for (const item of items) {
                                                    if (item.type.indexOf('image') !== -1) {
                                                        const blob = item.getAsFile();
                                                        const reader = new FileReader();
                                                        reader.onload = () => {
                                                            const dataUrl = reader.result;
                                                            Streamlit.setComponentValue(dataUrl);
                                                        };
                                                        reader.readAsDataURL(blob);
                                                        return;
                                                    }
                                                }
                                                Streamlit.setComponentValue(null);
                                            });
                                            window.focus();
                                        </script>
                                        </body>
                                        </html>
                                        """,
                                        height=220,
                                )
                                if paste_component:
                                        try:
                                                header, encoded = paste_component.split(',', 1)
                                                decoded = base64.b64decode(encoded)
                                                pil_img = Image.open(io.BytesIO(decoded)).convert('RGB')
                                                st.session_state['pasted_image'] = pil_img
                                                st.success('Imagem colada via navegador.')
                                        except Exception as e:
                                                st.error(f'Erro ao processar imagem colada: {e}')