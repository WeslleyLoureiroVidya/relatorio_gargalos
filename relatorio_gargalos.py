import os
import sys
import requests
import html
import re
from datetime import datetime, timedelta
from collections import Counter
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
# CONFIGURAÇÕES
# ============================================================
MOVIDESK_TOKEN = os.environ.get("MOVIDESK_TOKEN")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_TO = [e.strip() for e in os.environ.get("EMAIL_TO", "").split(",") if e.strip()]

faltando = []
if not MOVIDESK_TOKEN: faltando.append("MOVIDESK_TOKEN")
if not EMAIL_USER: faltando.append("EMAIL_USER")
if not EMAIL_PASSWORD: faltando.append("EMAIL_PASSWORD")
if not EMAIL_TO: faltando.append("EMAIL_TO")

if faltando:
    print(f"[ERRO] Variáveis de ambiente ausentes: {', '.join(faltando)}")
    sys.exit(1)

# ============================================================
# BUSCAR TICKETS
# ============================================================
hoje = datetime.now()
sete_dias_atras = hoje - timedelta(days=7)
data_filtro = sete_dias_atras.strftime("%Y-%m-%dT00:00:00Z")

url_tickets = "https://api.movidesk.com/public/v1/tickets"
params = {
    "token": MOVIDESK_TOKEN,
    "$filter": f"createdDate ge {data_filtro}",
    "$select": "subject,category,urgency,createdDate",
    "$top": "1000"
}

print(f"[DEBUG] Buscando tickets desde: {data_filtro}")
response = requests.get(url_tickets, params=params)

if not response.ok:
    print(f"[ERRO] Falha na API Movidesk: {response.status_code} - {response.text[:1000]}")
    tickets = []
else:
    try:
        tickets = response.json()
    except ValueError:
        tickets = []

    if not isinstance(tickets, list):
        tickets = []

    print(f"[DEBUG] Total de tickets encontrados: {len(tickets)}")

# ============================================================
# PROCESSAMENTO INTELIGENTE DE TEXTO E GARGALOS
# ============================================================
categorias = Counter()
urgencias = Counter()
palavras_soltas = Counter()
pares_palavras = Counter()

# Stopwords estendidas + remoção da palavra "assunto" e variações comuns de ruído
STOPWORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não", 
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", 
    "ao", "ele", "das", "tem", "seu", "sua", "ou", "ser", "quando", "muito", "nos", 
    "já", "está", "eu", "também", "pelo", "pela", "ate", "isso", "ela", "entre", 
    "depois", "sem", "mesmo", "aos", "ter", "seus", "quem", "nas", "me", "esse", 
    "eles", "você", "essa", "num", "nem", "suas", "meu", "minha", "numa", "pelos", 
    "elas", "qual", "nós", "lhe", "deles", "essas", "esses", "pelas", "este", "fosse", 
    "dele", "tu", "te", "ces", "vos", "lhes", "meus", "minhas", "teu", "tua", "teus", 
    "tuas", "nosso", "nossa", "nossos", "nossas", "dela", "delas", "esta", "estes", 
    "estas", "aquele", "aquela", "aqueles", "aquelas", "aquilo", "estou", "está", 
    "estamos", "estão", "estive", "esteve", "estivemos", "estiveram", "estava", 
    "estávamos", "estavam", "estivera", "estivéramos", "esteja", "estejamos", 
    "estejam", "estivesse", "estivéssemos", "estivessem", "estiver", "estivermos", 
    "estiverem", "hei", "há", "havemos", "hão", "houve", "houvemos", "houveram", 
    "houvera", "houvéramos", "haja", "hajamos", "hajam", "houvesse", "houvéssemos", 
    "houvessem", "houver", "houvermos", "houverem", "houverei", "houverá", "houveremos", 
    "houverão", "houveria", "houveríamos", "houveriam", "sou", "somos", "são", "era", 
    "éramos", "eram", "fui", "foi", "fomos", "foram", "fora", "fôramos", "seja", 
    "sejamos", "sejam", "fosse", "fôssemos", "fossem", "for", "formos", "forem", 
    "tenho", "tem", "temos", "tém", "tinha", "tínhamos", "tinham", "tive", "teve", 
    "tivemos", "tiveram", "tivera", "tivéramos", "tenha", "tenhamos", "tenham", 
    "tivesse", "tivéssemos", "tivessem", "tiver", "tivermos", "tiverem", "terei", 
    "terá", "teremos", "terão", "teria", "teríamos", "teriam",
    # Palavras personalizadas de ruído para suporte
    "assunto", "assuntos", "ticket", "tickets", "chamado", "chamados", "favor", 
    "preciso", "precisam", "ola", "boa", "tarde", "dia", "bom", "suporte", "ajuda", 
    "problema", "erro", "sistema"
}

def extrair_texto(campo):
    if campo is None: return None
    if isinstance(campo, str): return campo
    if isinstance(campo, dict):
        for chave in ("name", "description", "title", "value"):
            if campo.get(chave): return str(campo[chave])
    return str(campo)

def limpar_texto(texto):
    if not texto: return []
    texto = texto.lower()
    # Remove acentos e caracteres especiais
    import unicodedata
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    return texto.split()

for t in tickets:
    cat = extrair_texto(t.get("category")) or "Sem Categoria"
    urg = extrair_texto(t.get("urgency")) or "Sem Urgência"
    sub = t.get("subject", "") or ""

    categorias[cat] += 1
    urgencias[urg] += 1

    palavras = [p for p in limpar_texto(sub) if p not in STOPWORDS and len(p) > 3]
    
    # Contagem de palavras isoladas
    for palavra in palavras:
        palavras_soltas[palavra] += 1

    # Contagem de pares de palavras (Bigramas - ex: "erro login", "senha bloqueada")
    for i in range(len(palavras) - 1):
        par = f"{palavras[i]} {palavras[i+1]}"
        pares_palavras[par] += 1

# ============================================================
# MONTAGEM DO HTML COM DESIGN MODERNO
# ============================================================
def criar_tabela_bonita(titulo, contador, max_linhas=8):
    if not contador:
        return f"""
        <div style="background: #ffffff; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #e2e8f0;">
            <h3 style="margin-top: 0; color: #1e293b; font-size: 16px;">{titulo}</h3>
            <p style="color: #64748b; font-size: 13px; margin: 0;">Nenhum registro encontrado.</p>
        </div>
        """
    
    total_itens = sum(contador.values()) if sum(contador.values()) > 0 else 1

    html_tab = f"""
    <div style="background: #ffffff; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
        <h3 style="margin-top: 0; color: #0f172a; font-size: 16px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;">{titulo}</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    """
    
    for item, qtd in contador.most_common(max_linhas):
        porcentagem = int((qtd / total_itens) * 100)
        html_tab += f"""
        <tr>
            <td style="padding: 10px 0; color: #334155; width: 60%; border-bottom: 1px solid #f8fafc;">
                <strong>{html.escape(str(item))}</strong>
            </td>
            <td style="padding: 10px 0; color: #64748b; text-align: right; width: 15%; border-bottom: 1px solid #f8fafc;">
                {qtd} un.
            </td>
            <td style="padding: 10px 0; text-align: right; width: 25%; border-bottom: 1px solid #f8fafc;">
                <div style="background: #f1f5f9; border-radius: 4px; overflow: hidden; width: 100%; height: 8px;">
                    <div style="background: #3b82f6; width: {max(porcentagem, 5)}%; height: 8px; border-radius: 4px;"></div>
                </div>
            </td>
        </tr>
        """
    html_tab += "</table></div>"
    return html_tab

html_body = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b;">
<div style="max-width: 700px; margin: 0 auto; padding: 30px 15px;">
    
    <!-- Cabeçalho -->
    <div style="background: linear-gradient(135deg, #1e293b, #0f172a); color: #ffffff; border-radius: 16px; padding: 30px; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #38bdf8; margin-bottom: 8px;">Inteligência de Suporte</div>
        <h1 style="margin: 0; font-size: 22px; font-weight: 700;">Relatório Analítico de Gargalos</h1>
        <p style="margin: 8px 0 0 0; font-size: 13px; color: #94a3b8;">Período: {sete_dias_atras.strftime('%d/%m/%Y')} até {hoje.strftime('%d/%m/%Y')} | Total analisado: <strong>{len(tickets)} chamados</strong></p>
    </div>

    <!-- Seções de Análise -->
    {criar_tabela_bonita("📌 Principais Assuntos / Termos Recorrentes (Pares)", pares_palavras, 6)}
    {criar_tabela_bonita("📂 Categorias com Maior Demanda", categorias, 6)}
    {criar_tabela_bonita("⚡ Distribuição por Urgência", urgencias, 5)}
    {criar_tabela_bonita("🔍 Palavras-Chave Isoladas Relevantes", palavras_soltas, 6)}

    <!-- Rodapé -->
    <div style="text-align: center; padding: 20px; font-size: 12px; color: #94a3b8;">
        Relatório gerado automaticamente pelo seu ecossistema de automações no GitHub Actions.
    </div>
</div>
</body>
</html>
"""

# ============================================================
# ENVIO DO E-MAIL
# ============================================================
if not tickets:
    print("[INFO] Nenhum ticket encontrado, abortando envio.")
    sys.exit(1)
else:
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(EMAIL_TO)
    msg["Subject"] = f"📊 Intelligence Report: Gargalos e Assuntos Recorrentes ({hoje.strftime('%d/%m')})"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("[INFO] E-mail analítico enviado com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar e-mail: {e}")
        sys.exit(1)
