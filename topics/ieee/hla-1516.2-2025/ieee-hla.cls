\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{ieee-hla}[2026/07/31 v1.0.1 Unofficial reusable IEEE HLA recreation class]

\LoadClass[10pt]{article}

\RequirePackage[
  paperwidth=612bp,
  paperheight=792bp,
  left=90bp,
  right=90bp,
  top=69bp,
  bottom=48bp
]{geometry}
\RequirePackage{fontspec}
\RequirePackage{graphicx}
\RequirePackage{xcolor}
\RequirePackage{tikz}
\RequirePackage{array}
\RequirePackage{tabularx}
\RequirePackage{enumitem}
\RequirePackage{ragged2e}
\RequirePackage{xparse}
\RequirePackage{calc}
\RequirePackage{etoolbox}
\RequirePackage[unicode=true,hidelinks]{hyperref}

\RequirePackage{ieee-hla-colors}
\RequirePackage{ieee-hla-base}
\RequirePackage{ieee-hla-lists}
\RequirePackage{ieee-hla-tables}
\RequirePackage{ieee-hla-notes}
\RequirePackage{ieee-hla-annexes}
\RequirePackage{ieee-hla-frontmatter}

\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\JustifyingParindent}{0pt}
\setlength{\parskip}{0pt}
\setlength{\emergencystretch}{0.35em}
\urlstyle{same}
