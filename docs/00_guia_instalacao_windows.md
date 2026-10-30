# Etapa 0 — Preparar o computador (Windows)

Objetivo: no fim deste guia, o projeto roda no seu PC e está publicado no GitHub.
Tempo estimado: 1 a 2 horas na primeira vez.

## 1. Instalar os programas

| Programa | Onde baixar | Atenção na instalação |
| --- | --- | --- |
| Python 3.12 ou 3.13 | python.org → Downloads | Marque **"Add python.exe to PATH"** na primeira tela |
| Git | git-scm.com → Download for Windows | Pode aceitar todas as opções padrão |
| VS Code | code.visualstudio.com | Marque "Adicionar ao PATH" e "Abrir com Code" no menu do Explorer |
| Extensão Python do VS Code | Dentro do VS Code: ícone de extensões → buscar "Python" (Microsoft) | — |
| Claude Code | Siga a instalação oficial em docs.claude.com (seção Claude Code) | — |

Confira se deu certo. Abra o **PowerShell** e digite, um de cada vez:

```powershell
python --version
git --version
code --version
```

Cada um deve responder com um número de versão. Se aparecer "não é reconhecido", feche e abra o
PowerShell de novo; se continuar, reinstale marcando a opção de PATH.

## 2. Colocar o projeto no lugar

1. Crie a pasta `C:\Projetos\` (ou outra de sua preferência).
2. Descompacte o `sistema-itr.zip` dentro dela, ficando `C:\Projetos\sistema-itr\`.
3. No PowerShell:

```powershell
cd C:\Projetos\sistema-itr
code .
```

O VS Code abre com o projeto.

## 3. Criar o ambiente virtual do Python

O ambiente virtual (`.venv`) é uma "caixa" com as bibliotecas só deste projeto, sem misturar com
outros. No terminal do VS Code (menu Terminal → Novo Terminal):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o segundo comando der erro de "execução de scripts desabilitada", rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

e repita. Com o ambiente ativo, o terminal mostra `(.venv)` no começo da linha.

## 4. Testar

```powershell
python src/checar_config.py
pytest
```

O primeiro deve terminar com "Configuração OK". O segundo, com todos os testes passando (`passed`).

## 5. Publicar no GitHub

1. Crie uma conta em github.com (se ainda não tiver).
2. Clique em **New repository**: nome `sistema-itr`, **Public**, sem marcar README nem .gitignore
   (o projeto já tem os dois).
3. No terminal do VS Code, troque `SEU-USUARIO` pelo seu usuário do GitHub:

```powershell
git config --global user.name "Seu Nome"
git config --global user.email "seu-email-do-github"
git init
git add .
git commit -m "Etapas 0 a 2: estrutura, políticas contábeis e plano de contas"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/sistema-itr.git
git push -u origin main
```

Na primeira vez, o Windows abre uma janela para você entrar na conta do GitHub.

## 6. A partir daqui

Abra o Claude Code dentro da pasta `C:\Projetos\sistema-itr` para as próximas etapas. Ele lê o
README e a pasta `docs/`, então entende onde o projeto parou.

Regra de ouro para o portfólio: antes de aceitar um arquivo novo, peça para ele explicar o que
cada parte faz e leia. Você precisa conseguir explicar o código numa entrevista.
