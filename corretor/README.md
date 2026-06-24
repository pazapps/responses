# Corretor de Provas IA

Este repositório contém um app Streamlit que corrige provas usando a API Gemini.

Deploy (Streamlit Community Cloud)

1. Crie um repositório no GitHub (você já tem: https://github.com/pazapps/responses).
2. Faça commit/push de todos os arquivos deste projeto (`app.py`, `requirements.txt`, etc.).
3. Acesse https://share.streamlit.io e conecte sua conta GitHub.
4. Selecione o repositório `pazapps/responses` e a branch correta e clique em Deploy.
5. Configure secrets (Settings → Secrets) no painel do app no Streamlit Cloud:
   - `GEMINI_API_KEY` = sua chave do Gemini (NÃO comite essa chave no repo).

Notes
- Não comite chaves no repositório. Use `st.secrets` ou variáveis de ambiente.
- Se preferir um frontend estático no GitHub Pages, posso gerar um template separado e um backend (FastAPI) para hospedar a API.

