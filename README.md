# Assinaturas de email da Orira

Todos os dias, esta automação:

1. lê os membros ativos do Google Workspace (nome e cargo do diretório);
2. gera a imagem da assinatura de quem ainda não a tem, ou de quem mudou de nome ou cargo;
3. publica as imagens no GitHub Pages;
4. define a assinatura no Gmail dessas pessoas, clicável para https://orira.app.

Quem já tem a assinatura certa não é tocado.

## Configuração (uma vez)

### 1. Repositório no GitHub

1. Cria um repositório novo (por exemplo `assinaturas`) e carrega para lá todos os ficheiros desta pasta.
2. Em **Settings › Pages**, escolhe **Deploy from a branch**, ramo `main`, pasta `/docs`, e guarda.
3. Anota o endereço que o GitHub mostra (por exemplo `https://orira.github.io/assinaturas`).

### 2. Conta de serviço (console.cloud.google.com)

1. Cria um projeto (por exemplo "Assinaturas Orira").
2. Em **APIs e serviços › Biblioteca**, ativa a **Gmail API** e a **Admin SDK API**.
3. Em **IAM e administração › Contas de serviço**, cria uma conta de serviço.
4. Abre-a, vai a **Chaves › Adicionar chave › Criar nova chave › JSON** e descarrega o ficheiro.
5. Copia o **ID de cliente** (número longo) da conta de serviço.

### 3. Autorização no Workspace (admin.google.com, como superadministrador)

1. Vai a **Segurança › Acesso e controlo de dados › Controlos de API › Gerir delegação ao nível do domínio**.
2. Clica em **Adicionar novo**, cola o ID de cliente e, nos âmbitos, cola (separados por vírgula):

   ```
   https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/gmail.settings.basic
   ```

### 4. Segredos e variáveis no GitHub

Em **Settings › Secrets and variables › Actions**:

| Tipo | Nome | Valor |
|---|---|---|
| Secret | `GOOGLE_SERVICE_ACCOUNT_JSON` | o conteúdo completo do ficheiro JSON |
| Variable | `ADMIN_EMAIL` | email de um superadministrador (por exemplo `tomas.leal@orira.app`) |
| Variable | `URL_BASE_IMAGENS` | o endereço do GitHub Pages do passo 1, sem barra no fim |
| Variable | `EXCLUIR` | opcional: emails a ignorar, separados por vírgulas |

Depois de guardares o segredo, apaga o ficheiro JSON do teu computador.

### 5. Primeira execução

No separador **Actions**, abre **Assinaturas de email** e clica em **Run workflow**.
A primeira execução define a assinatura de toda a equipa. A partir daí corre sozinha todos os dias de manhã.

## Dia a dia

- **Novo membro:** cria a conta no Workspace e preenche o **cargo** (Diretório › Utilizadores › a pessoa › Informações do funcionário). Na manhã seguinte tem a assinatura. Para ser imediato, clica em **Run workflow**.
- **Mudança de cargo ou de nome:** altera no Workspace; a imagem é refeita na execução seguinte.
- **Sem cargo preenchido:** a pessoa é ignorada, e o registo da execução indica quem ficou de fora.
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
- A conta de serviço consegue alterar as definições de Gmail de toda a equipa. Guarda a chave só como segredo do GitHub.
