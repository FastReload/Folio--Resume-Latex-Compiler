import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file, abort
from dotenv import load_dotenv, set_key

load_dotenv()

app = Flask(__name__)

ENV_PATH     = str(Path(__file__).parent / '.env')
CONTEXT_PATH = str(Path(__file__).parent / 'base_context.txt')

SERVE_DIR = Path(__file__).parent / "compiled_pdfs"
SERVE_DIR.mkdir(exist_ok=True)

# Detect available compilers at startup
COMPILERS = {}
for name in ("xelatex", "pdflatex", "lualatex"):
    path = shutil.which(name)
    if path:
        COMPILERS[name] = path
        print(f"[OK] {name} found at: {path}")
    else:
        print(f"[--] {name} not found")

if not COMPILERS:
    print("\n[WARNING] No LaTeX compiler found on PATH.")
    print("          Install MiKTeX from https://miktex.org/download")
    print("          Then restart your terminal and run this script again.\n")


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\-]", "_", name.strip())
    return cleaned or "output"


def safe_rmtree(path: str) -> None:
    try:
        shutil.rmtree(path)
    except Exception:
        pass


# pdfTeX primitives that don't exist in XeLaTeX/LuaLaTeX.
# We inject no-op definitions right after \documentclass so that any package
# which does \input{glyphtounicode} (or similar) doesn't crash.
_XELATEX_COMPAT_SHIM = r"""
% -- XeLaTeX compatibility: silence pdfTeX-only primitives --
\makeatletter
\providecommand\pdfglyphtounicode[2]{}
\providecommand\pdfinfo[1]{}
\providecommand\pdfsuppresswarningpagegroup[0]{}
\makeatother
% -----------------------------------------------------------
"""

def preprocess_for_xelatex(code: str) -> str:
    """
    Prepare a pdfLaTeX document for XeLaTeX/LuaLaTeX:
      1. Strip raw pdfTeX register assignments  (e.g. \\pdfgentounicode=1)
         — these are primitives, not macros, so they can't be shimmed.
      2. Inject no-op \\providecommand definitions for pdfTeX *commands*
         (e.g. \\pdfglyphtounicode used inside glyphtounicode.tex)
         right after \\documentclass, before any \\usepackage calls.
    """
    # Step 1 — remove bare pdfTeX integer-register assignments like \pdfgentounicode=1
    code = re.sub(r'\\pdf[A-Za-z]+=\s*\d+', '', code)

    # Step 2 — inject shim after \documentclass{...}
    m = re.search(r'(\\documentclass(?:\[[^\]]*\])?\{[^}]+\})', code)
    if m:
        pos = m.end()
        return code[:pos] + "\n" + _XELATEX_COMPAT_SHIM + code[pos:]
    return _XELATEX_COMPAT_SHIM + code


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/compile", methods=["POST"])
def compile_latex():
    data = request.get_json(force=True)
    code = (data.get("code") or "").strip()
    raw_filename = (data.get("filename") or "output").strip()
    output_dir = (data.get("output_dir") or "").strip()
    compiler_name = "xelatex"

    if not code:
        return jsonify(success=False, log="No LaTeX code provided.", pdf_url=None)

    # output_dir is optional — only used when the user clicks Download
    save_to_dir = bool(output_dir)

    if not COMPILERS:
        return jsonify(
            success=False,
            log=(
                "No LaTeX compiler found on PATH.\n\n"
                "Please install MiKTeX:\n"
                "  1. Go to https://miktex.org/download\n"
                "  2. Download and install the Windows installer\n"
                "  3. Restart your terminal\n"
                "  4. Restart this app (python app.py)"
            ),
            pdf_url=None,
        )

    if compiler_name not in COMPILERS:
        # Fall back to whatever is available
        compiler_name = next(iter(COMPILERS))

    compiler_path = COMPILERS[compiler_name]
    filename = sanitize_filename(raw_filename)

    if save_to_dir:
        out_path = Path(output_dir).resolve()
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return jsonify(
                success=False,
                log=f"Could not create output directory '{output_dir}':\n{e}",
                pdf_url=None,
            )
    else:
        out_path = None

    tmpdir = tempfile.mkdtemp()
    try:
        # XeLaTeX/LuaLaTeX don't have pdfTeX primitives — patch them out
        if compiler_name in ("xelatex", "lualatex"):
            code = preprocess_for_xelatex(code)

        tex_file = os.path.join(tmpdir, filename + ".tex")
        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            [
                compiler_path,
                "-interaction=nonstopmode",
                f"-output-directory={tmpdir}",
                tex_file,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=tmpdir,
        )

        log = result.stdout
        if result.stderr:
            log += "\n" + result.stderr

        pdf_in_tmp = Path(tmpdir) / (filename + ".pdf")

        if pdf_in_tmp.exists():
            # Always copy to SERVE_DIR so the iframe can display it
            serve_dest = SERVE_DIR / (filename + ".pdf")
            shutil.copy2(str(pdf_in_tmp), str(serve_dest))
            # Only copy to user's output folder when this is a Download request
            if save_to_dir and out_path:
                shutil.copy2(str(pdf_in_tmp), str(out_path / (filename + ".pdf")))
            return jsonify(success=True, log=log, pdf_url=f"/pdf/{filename}")
        else:
            error_log = log or "Compilation failed — no PDF produced."
            return jsonify(success=False, log=error_log, pdf_url=None)

    except subprocess.TimeoutExpired:
        return jsonify(
            success=False,
            log="Compilation timed out after 120 seconds.",
            pdf_url=None,
        )
    except FileNotFoundError:
        return jsonify(
            success=False,
            log=f"{compiler_name} executable not found. Please install MiKTeX.",
            pdf_url=None,
        )
    except Exception as e:
        return jsonify(success=False, log=f"Internal error: {e}", pdf_url=None)
    finally:
        safe_rmtree(tmpdir)


@app.route("/pdf/<filename>")
def serve_pdf(filename):
    safe = sanitize_filename(filename)
    path = SERVE_DIR / (safe + ".pdf")
    if not path.exists():
        abort(404)
    return send_file(str(path), mimetype="application/pdf")


@app.route("/config", methods=["GET"])
def get_config():
    provider    = os.environ.get('AI_PROVIDER', '')
    model       = os.environ.get('AI_MODEL', '')
    api_key     = os.environ.get('AI_API_KEY', '')
    base_context = ''
    if os.path.exists(CONTEXT_PATH):
        with open(CONTEXT_PATH, 'r', encoding='utf-8') as f:
            base_context = f.read()
    key_preview = f"...{api_key[-4:]}" if len(api_key) >= 4 else ''
    return jsonify(
        provider=provider,
        model=model,
        key_set=bool(api_key),
        key_preview=key_preview,
        base_context=base_context,
    )


@app.route("/config", methods=["POST"])
def save_config():
    data         = request.get_json(force=True)
    provider     = (data.get('provider') or '').strip()
    api_key      = (data.get('api_key') or '').strip()
    model        = (data.get('model') or '').strip()
    base_context = data.get('base_context', '')

    if not provider or not model:
        return jsonify(success=False, error="Provider and model are required.")

    set_key(ENV_PATH, 'AI_PROVIDER', provider)
    set_key(ENV_PATH, 'AI_MODEL', model)
    os.environ['AI_PROVIDER'] = provider
    os.environ['AI_MODEL']    = model

    if api_key:
        set_key(ENV_PATH, 'AI_API_KEY', api_key)
        os.environ['AI_API_KEY'] = api_key

    with open(CONTEXT_PATH, 'w', encoding='utf-8') as f:
        f.write(base_context)

    return jsonify(success=True)


@app.route("/generate", methods=["POST"])
def generate_resume():
    data = request.get_json(force=True)
    jd   = (data.get('jd') or '').strip()

    if not jd:
        return jsonify(success=False, error="Job description is required.")

    provider = os.environ.get('AI_PROVIDER', '')
    api_key  = os.environ.get('AI_API_KEY', '')
    model    = os.environ.get('AI_MODEL', '')

    if not provider or not api_key or not model:
        return jsonify(success=False, error="AI not configured. Click ⚙ Settings to set up.")

    base_context = ''
    if os.path.exists(CONTEXT_PATH):
        with open(CONTEXT_PATH, 'r', encoding='utf-8') as f:
            base_context = f.read()

    system_prompt = (
        "You are an expert resume writer and LaTeX specialist.\n"
        "Generate a complete, professional LaTeX resume tailored to the provided job description.\n\n"
        "Use the following resume context as the foundation for the candidate's background:\n"
        + base_context +
        "\n\nRules:\n"
        "1. Output ONLY valid LaTeX code — no explanations, no markdown, no code fences.\n"
        "2. Keep ALL the candidate's real experience, projects, and skills from the context.\n"
        "3. Tailor bullet points and emphasis to match the job description keywords.\n"
        "4. Use a clean, ATS-friendly LaTeX format.\n"
        "5. The output must start with \\documentclass and end with \\end{document}."
    )
    user_prompt = f"Generate a tailored LaTeX resume for this job description:\n\n{jd}"

    try:
        if provider == 'anthropic':
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=api_key)
            msg    = client.messages.create(
                model=model, max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            latex = msg.content[0].text

        elif provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp   = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            latex = resp.choices[0].message.content

        elif provider == 'gemini':
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            resp   = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=4096,
                ),
            )
            latex = resp.text

        else:
            return jsonify(success=False, error=f"Unknown provider: {provider}")

        # Strip markdown code fences in case the model wraps output
        latex = latex.strip()
        if latex.startswith('```'):
            latex = re.sub(r'^```[^\n]*\n', '', latex)
            latex = re.sub(r'\n```\s*$', '', latex)

        return jsonify(success=True, latex=latex)

    except Exception as e:
        return jsonify(success=False, error=str(e))


if __name__ == "__main__":
    print("\n  LaTeX Compiler running at http://127.0.0.1:8501\n")
    app.run(debug=True, host="127.0.0.1", port=8501, use_reloader=False)
