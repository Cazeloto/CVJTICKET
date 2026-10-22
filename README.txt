CVJFILAS - versão modular (Flet 0.80+)

Chamada pelo celular:
- Com o sistema rodando, conecte o celular à mesma rede do computador.
- Abra http://IP-DO-COMPUTADOR:8123/celular (use a porta APP_PORT se alterada).
- A rota /celular/chamada também abre a chamada.
- Selecione Preferencial, Normal, Espera ou Ausente. O botão inferior
  "Chamar próximo" chama a próxima senha aguardando na fila selecionada.
- "Adicionar à espera" cadastra quem chegou depois, sem sair da chamada.
  Informe o nome e confirme: a senha entra na fila Espera do dia.
- Os botões Chamar novamente, Concluir e Não apareceu ficam em cada cartão.
- /celular/cadastro permite cadastrar também nas filas Normal e Preferencial.
- O computador deve permanecer ligado; a rede precisa permitir acesso à porta.

Como rodar (web):
1) Copie a pasta 'cvjfilas' e o arquivo 'run.py' para a raiz do seu projeto (C:\CVJFILASNEW)
2) Garanta que a pasta 'services' continua igual (DatabaseService, PrintService)
3) Rode:
   .venv\Scripts\python.exe run.py

O que pode apagar do app.py original:
- Tudo do app.py original pode ser substituído por 'run.py' + pacote 'cvjfilas'.
- Mantenha: pasta services/, pasta assets/, e quaisquer outros módulos do projeto (pdf/, db/, etc).
