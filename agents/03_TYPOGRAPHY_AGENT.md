# 🔤 Agente 03: Typography & Graphic Engine

**Localização no Código:** [app/services/graphics/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/graphics/)  
**Arquivos Chave:** [graphics_engine.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/graphics/graphics_engine.py), [number_card.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/graphics/number_card.py), [text_card.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/graphics/text_card.py), [theme.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/graphics/theme.py)

---

## 1. Missão do Agente

O **Typography & Graphic Engine** garante que o texto na tela não seja apenas uma legenda passiva, mas uma ferramenta ativa de impacto, síntese e retenção em telas de celulares verticais (1080x1920).

Ele resolve dois problemas graves identificados no protótipo:
1. **Textos minúsculos e ilegíveis** em telas pequenas.
2. **Textos cortados ou ocultados pela interface** dos aplicativos (TikTok, Instagram Reels, YouTube Shorts).

---

## 2. Os Três Níveis de Hierarquia Gráfica

| Nível | Tipo | Tamanho / Estilo | Função Editorial | Exemplo |
| :--- | :--- | :--- | :--- | :--- |
| **Nível 1** | `TITLE` | **64pt – 96pt**<br>Caixa alta, peso pesado, contraste preto/amarelo ou branco/vermelho | Choque de impacto, números de preço, perguntas provocativas | `"R$ 79,90"`<br>`"QUEM FEZ ISSO?"` |
| **Nível 2** | `EMPHASIS` | **42pt – 56pt**<br>Caixa de destaque estilizada, máximo 2 linhas | Conceitos-chave e contrastes | `"TRANSFORME TRABALHO EM VALOR"` |
| **Nível 3** | `CAPTION` | **28pt – 36pt**<br>Fundo arredondado semi-transparente, alta legibilidade | Legenda de acompanhamento da narração falada | Transcrição dinâmica |

---

## 3. O Mapa da Safe Area 9:16 Vertical (1080x1920)

Todo renderizador de texto DEVE obedecer estritamente à zona segura:

```
      0 px ┌────────────────────────────────────────┐
           │     ZONA PROIBIDA - TOPO (250 px)      │ ➔ Ocultado por abas, buscas, som
    250 px ├────────────────────────────────────────┤
           │                                        │
           │                                        │
           │            SAFE AREA                   │
           │                                        │
           │    Margem lateral: 60 px de cada lado  │
           │    Largura máxima de texto: 960 px     │
           │                                        │
           │                                        │
   1570 px ├────────────────────────────────────────┤
           │     ZONA PROIBIDA - BASE (350 px)      │ ➔ Ocultado por botões de like, share,
   1920 px └────────────────────────────────────────┘   comentários, nome do perfil e áudio
```

### Regras Matemáticas:
- $Y_{\text{mínimo}} \ge 250\text{ px}$
- $Y_{\text{máximo}} \le 1570\text{ px}$
- $X_{\text{mínimo}} \ge 60\text{ px}$
- $X_{\text{máximo}} \le 1020\text{ px}$
- Violações dessa regra são rejeitadas pelo `QualityChecker` com o erro `text_outside_safe_area`.
