# Assinaturas de email da Orira

Todos os dias, esta automação:

1. lê os membros ativos do Google Workspace (nome e cargo do diretório);
2. gera a imagem da assinatura de quem ainda não a tem, ou de quem mudou de nome ou cargo;
3. publica as imagens no GitHub Pages;
4. define a assinatura no Gmail dessas pessoas, clicável para https://orira.app.

Quem já tem a assinatura certa não é tocado.

## Configuração (uma vez)

### 1. Repositório no GitHub

1. Carrega estes ficheiros para um repositório (por exemplo `assinaturas`).
2. Em **Settings › Pages**, em **Source**, escolhe **GitHub Actions**. O próprio fluxo publica as imagens (um push feito pelo Actions não reconstrói o Pages sozinho).
3. O endereço das imagens fica `https://<conta>.github.io/assinaturas`.

### 2. Google Cloud, sem chave (Workload Identity Federation)

O GitHub Actions entra no Google Cloud sem ficheiro de chave: o Google confia nos tokens que o GitHub emite para este repositório, e só para ele. Nas organizações criadas depois de maio de 2024 a criação de chaves está bloqueada por defeito, e assim não há nenhuma chave para perder.

Com o `gcloud` (substitui `PROJETO` e `CONTA/REPO`):

```
gcloud projects create PROJETO --name="Assinaturas Orira"
gcloud config set project PROJETO
gcloud services enable gmail.googleapis.com admin.googleapis.com iamcredentials.googleapis.com
gcloud iam service-accounts create assinaturas --display-name="Assinaturas de email"
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers create-oidc assinaturas --location=global   --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com   --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"   --attribute-condition="assertion.repository=='CONTA/REPO'"
gcloud iam service-accounts add-iam-policy-binding assinaturas@PROJETO.iam.gserviceaccount.com   --role=roles/iam.serviceAccountTokenCreator   --member="principalSet://iam.googleapis.com/projects/NUMERO_DO_PROJETO/locations/global/workloadIdentityPools/github/attribute.repository/CONTA/REPO"
gcloud iam service-accounts describe assinaturas@PROJETO.iam.gserviceaccount.com --format="value(oauth2ClientId)"
```

O último comando mostra o **ID de cliente** (número longo) da conta de serviço.

### 3. Autorização no Workspace (admin.google.com, como superadministrador)

1. Vai a **Segurança › Acesso e controlo de dados › Controlos de API › Gerir delegação ao nível do domínio**.
2. Clica em **Adicionar novo**, cola o ID de cliente e, nos âmbitos, cola (separados por vírgula):

   ```
   https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/gmail.settings.basic
   ```

### 4. Variáveis no GitHub

Em **Settings › Secrets and variables › Actions › Variables**:

| Nome | Valor |
|---|---|
| `WIF_PROVIDER` | `projects/NUMERO_DO_PROJETO/locations/global/workloadIdentityPools/github/providers/assinaturas` |
| `CONTA_SERVICO` | `assinaturas@PROJETO.iam.gserviceaccount.com` |
| `ADMIN_EMAIL` | email de um superadministrador do Workspace |
| `URL_BASE_IMAGENS` | o endereço do GitHub Pages do passo 1, sem barra no fim |
| `EXCLUIR` | opcional: emails a ignorar, separados por vírgulas |

Em alternativa à federação, ainda funciona com uma chave JSON no secret `GOOGLE_SERVICE_ACCOUNT_JSON` (sem `WIF_PROVIDER`).

### 5. Primeira execução

No separador **Actions**, abre **Assinaturas de email** e clica em **Run workflow**.
A primeira execução define a assinatura de toda a equipa. A partir daí corre sozinha todos os dias de manhã.
Antes de mexer no Gmail de alguém, o fluxo confirma que a imagem dessa pessoa já responde no endereço público; se não responder, fica para a execução seguinte.

## Dia a dia

- **Novo membro:** cria a conta no Workspace e preenche o **cargo** (Diretório › Utilizadores › a pessoa › Informações do funcionário). Na manhã seguinte tem a assinatura. Para ser imediato, clica em **Run workflow**.
- **Mudança de cargo ou de nome:** altera no Workspace; a imagem é refeita na execução seguinte.
- **Sem cargo preenchido:** a pessoa é ignorada, e o registo da execução indica quem ficou de fora.
- **Linha legal:** por baixo da imagem vai, em texto, a firma, o NIPC e um link "Dados legais" para a página de contactos (art. 171.º do CSC). Muda-se nas constantes `EMPRESA` e `NIPC` do `sincronizar.py`; alterá-las volta a aplicar a assinatura a todos.
- **Mudar o design:** edita `recursos/modelo.html` (ou troca `recursos/logo.png`); todas as assinaturas são refeitas na execução seguinte.

## Experimentar no teu computador

```
pip install -r requirements.txt
python -m playwright install chromium
python sincronizar.py gerar --csv membros.csv     # colunas: email,nome,cargo
python sincronizar.py aplicar --dry-run
```

As imagens aparecem em `docs/`. Nenhum destes dois comandos altera contas de Gmail.

## A saber

- A assinatura substitui a que cada pessoa tiver no Gmail.
- O GitHub Pages é público: as imagens e os ficheiros `docs/estado.json` e `docs/pendentes.json` (emails, nomes e cargos) ficam acessíveis a quem souber o endereço. Num plano gratuito do GitHub, o repositório também tem de ser público.
- A conta de serviço consegue alterar as definições de Gmail de toda a equipa. Só este repositório a pode usar (condição do fornecedor de identidade).
