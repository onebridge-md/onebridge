# OneBridge - OneNote Integration Layer & CLI

Camada de integração e interface de linha de comando (CLI) para acesso e sincronização de dados com o Microsoft OneNote (Microsoft Graph API), com suporte a contas pessoais (MSA) e corporativas/educacionais (Microsoft 365 / Entra ID).

---

## 🔐 Como Funciona a Autenticação e Persistência

1. **OAuth 2.0 Moderno (MSAL)**: Utiliza a biblioteca oficial da Microsoft (**MSAL**).
2. **Sem necessidade de pedir senha repetidamente**: O login inicial gera um `Access Token` e um `Refresh Token` (`offline_access`).
3. **Persistência Segura em SQLite**: O Token Cache do MSAL é criptografado localmente e salvo na tabela `token_cache` do banco SQLite (`~/.onebridge/auth.db`).
4. **Renovação Silenciosa**: Em execuções subsequentes, o sistema renova os tokens em segundo plano via `acquire_token_silent()`, sem qualquer intervenção do usuário.

---

## 🚀 Instalação

```bash
cd ~/development/onebridge
pip install -e .
```

---

## 💻 Uso da CLI

### 1. Fazer Login
Por padrão, inicia o **Device Code Flow** (ideal para terminais e servidores remotos):
```bash
onebridge login
```
Será exibido:
```
============================================================
To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABCD-1234 to authenticate.
============================================================
```
Você pode abrir o link no seu navegador (desktop ou smartphone), digitar o código e aprovar.

Para abrir o navegador local diretamente:
```bash
onebridge login --method browser
```

### 2. Verificar Status e Conta Conectada
```bash
onebridge status
```
Exemplo de saída:
```
🔎 Verificando validade da sessão...
✅ Autenticado com sucesso!
👤 Nome:      Fulano de Tal
📧 E-mail:    fulano@outlook.com
🆔 ID:        12345678-abcd-ef01-2345-6789abcdef01
📅 Atualizado: 2026-09-06 17:00:00
📁 Banco DB:  /home/user/.onebridge/auth.db
```

### 3. Fazer Logout
```bash
onebridge logout
```

### 4. Listar Cadernos (Notebooks)
```bash
onebridge list-notebooks
onebridge list-notebooks --json
onebridge list-notebooks --sort-by name
```

### 5. Listar Seções (Sections)
```bash
onebridge list-sections "Meu Caderno"
onebridge list-sections "Meu Caderno" --tree
onebridge list-sections "Meu Caderno" --format csv
```

### 6. Definir Contexto Padrão (`set-notebook` e `set-section`)
Defina o caderno e a seção padrão para evitar ter que digitar seus nomes/IDs repetidamente nos comandos:
```bash
# Definir e verificar caderno padrão
onebridge set-notebook "Caderno Pessoal"
onebridge set-notebook --show
onebridge set-notebook --clear

# Definir e verificar seção padrão
onebridge set-section "Tarefas"
onebridge set-section --show
onebridge set-section --clear
```

### 7. Listar Páginas (`list-pages`)
```bash
# Listar páginas da seção padrão ativa
onebridge list-pages

# Listar páginas de uma seção específica
onebridge list-pages "Anotações Gerais"
onebridge list-pages "Anotações Gerais" --notebook "Caderno Pessoal"

# Formatos de saída e ordenação
onebridge list-pages "Anotações Gerais" --format table
onebridge list-pages "Anotações Gerais" --json
onebridge list-pages "Anotações Gerais" --sort-by title --asc
onebridge list-pages "Anotações Gerais" --sort-by modified --desc
```


---

## ⚙️ Configuração Personalizada (Opcional)

Se desejar utilizar sua própria aplicação registrada no portal do Azure/Entra ID:

1. Registre uma aplicação no [Azure Portal (App Registrations)](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Defina os tipos de conta suportados: **Contas em qualquer diretório organizacional e contas pessoais da Microsoft** (`common`).
3. Em **Autenticação**, adicione uma plataforma **Mobile and desktop applications** e marque a opção de cliente público (`Allow public client flows: Yes`).
4. Configure as variáveis de ambiente:
   ```bash
   export ONEBRIDGE_CLIENT_ID="seu-client-id-aqui"
   export ONEBRIDGE_DB_PATH="caminho/para/outro/auth.db"
   ```

---

## 🧪 Executando os Testes

```bash
cd ~/development/onebridge
pytest
```
