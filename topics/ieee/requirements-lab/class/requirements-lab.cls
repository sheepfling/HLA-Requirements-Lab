\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{requirements-lab}[2026/08/23 v0.1 Requirements Lab publishing system]

\LoadClass[10pt,oneside]{article}

\RequirePackage[
    paperwidth=612bp,
    paperheight=792bp,
    left=0.82in,
    right=0.82in,
    top=0.70in,
    bottom=0.72in,
    headheight=24pt,
    headsep=18pt,
    footskip=24pt
]{geometry}
\RequirePackage{fontspec}
\RequirePackage{graphicx}
\RequirePackage{xcolor}
\RequirePackage{tikz}
\usetikzlibrary{arrows.meta,positioning}
\RequirePackage{array}
\RequirePackage{booktabs}
\RequirePackage{longtable}
\RequirePackage{tabularx}
\RequirePackage{enumitem}
\RequirePackage{fancyhdr}
\RequirePackage{pdflscape}
\RequirePackage{titlesec}
\RequirePackage{amsmath}
\RequirePackage{xparse}
\RequirePackage{ragged2e}
\RequirePackage{microtype}
\RequirePackage[unicode=true,hidelinks]{hyperref}

% The shared layer lives beside the HLA topic products. Keeping these inputs
% here makes every topic a thin profile over one publishing system.
\input{../requirements-lab/style/rl-brand.sty}
\input{../requirements-lab/style/rl-graphics.sty}
\input{../requirements-lab/style/rl-type.sty}
\input{../requirements-lab/style/rl-links.sty}
\input{../requirements-lab/style/rl-page.sty}
\input{../requirements-lab/style/rl-headings.sty}
\input{../requirements-lab/style/rl-tables.sty}
\input{../requirements-lab/style/rl-code.sty}
\input{../requirements-lab/style/rl-math.sty}
\input{../requirements-lab/style/rl-notes.sty}
\input{../requirements-lab/style/rl-frontmatter.sty}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0.62em}
\setlength{\emergencystretch}{1em}
\RaggedRight
% Ragged-right prose intentionally leaves flexible line endings. Keep those
% expected underfull notices quiet while retaining visible overfull-box QA.
\hbadness=10000
\color{RLInk}
\setlist{nosep}
\urlstyle{same}
\RLEnablePageStyle
