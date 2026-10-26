import re, os

INPUT = "paper_v2.md"
OUTPUT = "paper/paper.tex"

with open(INPUT, "r", encoding="utf-8") as f:
    md = f.read()

def escape_latex(s):
    s = s.replace("&", r"\&")
    s = s.replace("%", r"\%")
    s = s.replace("$", r"\$")
    s = s.replace("#", r"\#")
    s = s.replace("_", r"\_")
    s = s.replace("{", r"\{")
    s = s.replace("}", r"\}")
    s = s.replace("~", r"\textasciitilde{}")
    s = s.replace("^", r"\textasciicircum{}")
    return s

def md_to_latex(md_text):
    lines = md_text.split("\n")
    latex_lines = []
    in_table = False
    table_lines = []
    in_list = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip horizontal rules
        if line.strip() == "---":
            i += 1
            continue

        # Headers
        if line.startswith("# "):
            # Title - skip, handled in preamble
            i += 1
            continue
        if line.startswith("## "):
            sec = line[3:].strip()
            if sec.startswith("Appendix"):
                latex_lines.append(r"\appendix" if "Appendix A" in sec else "")
                letter = sec.split(":")[0].replace("Appendix ", "")
                title = sec.split(":", 1)[1].strip() if ":" in sec else sec
                latex_lines.append(f"\\section{{{title}}}\\label{{app:{letter.lower()}}}")
            elif sec == "References":
                latex_lines.append(r"\bibliographystyle{plain}")
                latex_lines.append(r"\begin{thebibliography}{99}")
                # Process references
                i += 1
                while i < len(lines):
                    rline = lines[i].strip()
                    if rline.startswith("## ") or rline == "---":
                        if rline == "---":
                            i += 1
                            continue
                        break
                    if rline and not rline.startswith("---"):
                        # Parse reference
                        rline = rline.replace("*", "")
                        key = rline.split(",")[0].split("(")[0].strip().lower().replace(" ", "").replace(".", "")
                        latex_lines.append(f"\\bibitem{{{key}}} {rline}")
                    i += 1
                latex_lines.append(r"\end{thebibliography}")
                continue
            else:
                num = sec.split(".")[0] if sec[0].isdigit() else ""
                latex_lines.append(f"\\section{{{sec}}}")
            i += 1
            continue
        if line.startswith("### "):
            sec = line[4:].strip()
            latex_lines.append(f"\\subsection{{{sec}}}")
            i += 1
            continue

        # Tables
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
            i += 1
            continue
        elif in_table:
            # End of table
            in_table = False
            latex_lines.extend(convert_table(table_lines))
            # Don't increment, process current line
            continue

        # Bold text markers
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            # Standalone bold line - make it a paragraph header
            content = line.strip("* ")
            latex_lines.append(f"\\noindent\\textbf{{{content}}}")
            latex_lines.append("")
            i += 1
            continue

        # Block quotes
        if line.startswith("> "):
            content = line[2:]
            content = process_inline(content)
            latex_lines.append(f"\\begin{{quote}}{content}\\end{{quote}}")
            i += 1
            continue

        # Numbered lists
        if re.match(r'^\d+\.\s', line.strip()):
            if not in_list:
                latex_lines.append(r"\begin{enumerate}")
                in_list = True
            content = re.sub(r'^\d+\.\s', '', line.strip())
            content = process_inline(content)
            latex_lines.append(f"  \\item {content}")
            i += 1
            continue
        elif in_list and (line.strip() == "" or not re.match(r'^\d+\.\s', line.strip())):
            latex_lines.append(r"\end{enumerate}")
            in_list = False
            if line.strip() == "":
                latex_lines.append("")
                i += 1
                continue

        # Bullet lists
        if line.strip().startswith("- "):
            content = line.strip()[2:]
            content = process_inline(content)
            latex_lines.append(f"\\begin{{itemize}}\\item {content}\\end{{itemize}}")
            i += 1
            continue

        # Regular paragraph text
        processed = process_inline(line)
        latex_lines.append(processed)
        i += 1

    if in_list:
        latex_lines.append(r"\end{enumerate}")

    return "\n".join(latex_lines)

def process_inline(text):
    # Bold + italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\\textbf{\\textit{\1}}', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'\\textit{\1}', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'\\texttt{\1}', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\\href{\2}{\1}', text)
    # Special chars (careful not to double-escape)
    text = text.replace("~", r"\textasciitilde{}")
    text = text.replace(">=", r"$\geq$")
    text = text.replace("<=", r"$\leq$")
    # Approximate symbol
    text = text.replace("approximately ", r"$\approx$")
    return text

def convert_table(tlines):
    result = []
    # Parse header
    header = [c.strip() for c in tlines[0].strip("|").split("|")]
    ncols = len(header)
    colspec = "l" * ncols

    result.append(f"\\begin{{table}}[h]\\centering\\small")
    result.append(f"\\begin{{tabular}}{{{colspec}}}")
    result.append(r"\hline")

    # Header row
    hdr = " & ".join(header) + r" \\"
    result.append(hdr)
    result.append(r"\hline")

    # Data rows (skip separator line)
    for tl in tlines[2:]:
        cells = [c.strip() for c in tl.strip("|").split("|")]
        row = " & ".join(cells) + r" \\"
        result.append(row)

    result.append(r"\hline")
    result.append(r"\end{tabular}")
    result.append(r"\end{table}")
    return result

# Extract title, authors, abstract
title_match = re.search(r'^# (.+)$', md, re.MULTILINE)
title = title_match.group(1) if title_match else "Paper"

# Extract abstract
abs_match = re.search(r'## Abstract\n\n(.+?)(?=\n\n\*\*Keywords)', md, re.DOTALL)
abstract = abs_match.group(1).strip() if abs_match else ""
abstract = process_inline(abstract)

# Remove title, author block, abstract, keywords from body
body_start = md.find("## 1.")
if body_start == -1:
    body_start = md.find("## 2.")
body = md[body_start:]

latex_body = md_to_latex(body)

# Build complete document
doc = rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{geometry}}
\geometry{{margin=1in}}
\usepackage{{hyperref}}
\hypersetup{{colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue}}
\usepackage{{booktabs}}
\usepackage{{enumitem}}
\usepackage{{amsmath}}
\usepackage{{graphicx}}
\usepackage{{float}}

\title{{{title}}}
\author{{Akanksha Gupta\\3am Labs; TARA (Technical AI Alignment Research Accelerator)\\\texttt{{akanksha@3amlabs.ai}} \and Claude Opus 4.6\\Anthropic}}
\date{{Apart Research Collusion Sprint 2026\\Track 2: Detection and Audit of Collusion}}

\begin{{document}}
\maketitle

\begin{{abstract}}
{abstract}
\end{{abstract}}

{latex_body}

\end{{document}}
"""

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(doc)

print(f"LaTeX written to {OUTPUT}")
