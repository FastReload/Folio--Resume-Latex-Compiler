import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file, abort

app = Flask(__name__)

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


if __name__ == "__main__":
    print("\n  LaTeX Compiler running at http://127.0.0.1:5000\n")
    app.run(debug=True, host="127.0.0.1", port=5000, use_reloader=False)
