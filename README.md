# Folio

**The fastest way to compile and download a LaTeX resume.**

Overleaf is great — until you're applying to 20 jobs and every tweak means creating a new project, renaming files, waiting for the cloud, and downloading through three menus. Folio cuts all of that. Paste your LaTeX, hit Preview, hit Download, give it a name, done. The whole thing takes seconds.

No projects. No file management. No accounts. Just your resume and a PDF.

---

## The problem with Overleaf for resumes

You tweak your resume for every application. Different company, different role, slightly different bullet points. In Overleaf that means:

- Create a new project (or duplicate an existing one and rename it)
- Wait for the editor to load
- Make your changes
- Compile — wait — compile again if it fails
- Download → go to your downloads folder → rename the file
- Repeat 20 times during recruiting season

It's a workflow built for long-term documents, not rapid one-off exports.

---

## How Folio works

1. Paste your LaTeX resume into the editor
2. Hit **Preview** — PDF appears instantly in the right panel
3. Hit **Download** — type `Amazon_SWE` or `Google_DS` or whatever you want — PDF lands in your folder

That's the whole flow. One window, no projects, no waiting.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Folio          Output folder: C:\Users\you\Resumes   [Preview] [↓] │
├────────────────────────────────┬─────────────────────────────────────┤
│                                │                                     │
│  \documentclass{article}       │      Your resume renders here       │
│  \usepackage{sourcesanspro}    │      live, in the browser           │
│  ...                           │                                     │
│  Paste your resume LaTeX       ├─────────────────────────────────────┤
│  Tweak a bullet point          │  ✓ Compiled successfully            │
│  Preview → Download → done     │                                     │
│                                │                                     │
└────────────────────────────────┴─────────────────────────────────────┘
```

---

## Features

- **Instant preview** — compile and render in the same window, no switching tabs or downloading to check
- **Named downloads** — filename prompt on every download so `Resume_Netflix.pdf` and `Resume_Stripe.pdf` go exactly where you want them, named correctly
- **XeLaTeX engine** — handles modern fonts (Source Sans Pro, FontAwesome5, custom typefaces) that pdfLaTeX chokes on
- **pdfLaTeX template support** — most resume templates on GitHub are built for pdfLaTeX; Folio automatically patches out the incompatible primitives so they compile without touching your source
- **Overleaf-style UI** — Source Sans Pro font, dark editor, same green, familiar feel
- **LaTeX syntax highlighting** — CodeMirror with full LaTeX mode so your source is readable
- **Remembers your folder** — set your output folder once, it sticks across sessions
- **Ctrl+Enter to compile** — keyboard-first workflow
- **Fully local** — runs on `localhost`, nothing leaves your machine

---

## Getting started

### You need

- Python 3.x
- [MiKTeX](https://miktex.org/download) — install it, let it run its setup, restart your terminal

### Setup

```bash
git clone https://github.com/yourusername/folio.git
cd folio
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

Set your output folder in the top bar. Paste your resume LaTeX. You're ready.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python + Flask |
| Compiler | XeLaTeX (MiKTeX) |
| Editor | CodeMirror 5 — LaTeX syntax, dracula theme |
| UI Font | Source Sans Pro |
| Preview | Browser-native PDF viewer |

---

## Project structure

```
folio/
├── app.py              # Flask backend
├── requirements.txt
├── templates/
│   └── index.html      # Everything — editor, preview, UI
└── compiled_pdfs/      # Internal serving cache (gitignored)
```

---

## License

MIT
