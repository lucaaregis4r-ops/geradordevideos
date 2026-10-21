# 🎙️ Agente 04: Audio Mastering & Voice Engineering

**Localização no Código:** [app/services/voice/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/voice/) / [app/services/audio/](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/audio/)  
**Arquivos Chave:** [voice.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/voice.py), [pronunciation.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/editorial/pronunciation.py), [video_project.py](file:///home/lucasregis/%C3%81rea%20de%20trabalho/Projetos/Backup/fabrica%20de%20bermudas/app/services/video_project.py)

---

## 1. Missão do Agente

O áudio é responsável por **mais de 50% da retenção e credibilidade** do ensaio audiovisual. O **Audio Mastering Agent** garante que:
1. A voz seja dominante, cristalina e padronizada nos padrões de loudness da internet contemporânea.
2. A variação de volume do protótipo (-19.8 LUFS com picos instáveis) seja eliminada.
3. A música de fundo nunca dispute atenção com o narrador.
4. Silêncios deliberados reforcem o peso dramático das perguntas reflexivas.

---

## 2. Padrões de Loudness e Masterização

O pipeline adota o padrão broadcast **EBU R128 / ITU-R BS.1770-4** adaptado para mídias sociais digitais:

| Parâmetro | Alvo | Filtro FFmpeg |
| :--- | :---: | :--- |
| **Integrated Loudness ($I$)** | **-14.0 LUFS** (±0.5 LUFS) | `loudnorm=I=-14.0:TP=-1.0:LRA=7` |
| **True Peak ($TP$)** | **-1.0 dBFS** (sem distorção/clipping) | Integrado ao `loudnorm` |
| **Loudness Range ($LRA$)** | **7.0 LU** (dinâmica controlada) | Integrado ao `loudnorm` |
| **Compressão Vocal** | Redução suave de picos | `acompressor=threshold=-20dB:ratio=3:attack=10:release=100` |
| **High-Pass Filter** | Limpeza de graves sujos (< 80 Hz) | `highpass=f=80` |

---

## 3. Ducking Automático de Trilha Sonora (Sidechain Ducking)

A música de fundo NÃO pode ter volume estático.

- **Quando a voz está ativa:** O volume da música recua automaticamente entre **-14 dB e -18 dB** (ducking).
- **Nas pausas da fala:** A música sobe suavemente (+6 dB a +8 dB) mantendo o ritmo.
- **Implementação via FFmpeg:**
  ```text
  [music][voice]sidechaincompress=threshold=0.08:ratio=4:attack=50:release=300[ducked_music];
  [ducked_music][voice]amix=inputs=2:duration=first:dropout_transition=2[aout]
  ```

---

## 4. Curva Dramática da Trilha

A música deve acompanhar a transformação do argumento (Seção 20 do Relatório):
- **Ato 1 (Início - Aspiração):** Trilha corporativa/eletrônica moderna confiante.
- **Ato 2 & 3 (Fábrica / Trabalho):** Redução progressiva da instrumentação.
- **Ato 4 & 5 (Revelação e Pergunta):** Corte da trilha ou silêncio absoluto para destacar a pergunta: *"Quem fez isso?"*.
