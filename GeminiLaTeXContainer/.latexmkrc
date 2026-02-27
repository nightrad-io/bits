# --- Core Engine and Behavior ---
# Set the default engine to LuaLaTeX and enable machine-readable errors.
$pdf_mode = 4;
$latalatex = 'lualatex -interaction=nonstopmode -file-line-error %O %S';

# --- Custom Compilation Rules for External Tools ---

# Rule for `musictex`, which is part of the `musixtex` package.
add_cus_dep('mx1', 'mx2', 0, 'run_musixflx');
sub run_musixflx {
  return run_system("musixflx", "%S");
}

# Rule for `glossaries-extra` (modern, fast `bib2gls` method).
add_cus_dep('glo', 'glstex', 0, 'run_bib2gls');
sub run_bib2gls {
  return run_system("bib2gls", "--group", "%S");
}

# Rule for `glossaries` (legacy `makeglossaries` method).
add_cus_dep('glo', 'gls', 0, 'makeglossaries %S');
add_cus_dep('acn', 'acr', 0, 'makeglossaries %S');

# Rule for `nomencl`.
add_cus_dep('nlo', 'nls', 0, 'makeindex -s nomencl.ist -o %D %S');

# --- File Cleanup Configuration ---
# Add auxiliary file extensions to the list for `latexmk -c`.
$clean_ext .= ' mx1 mx2 mxs';             # musixtex
$clean_ext .= ' acr acn alg glo gls glg'; # makeglossaries
$clean_ext .= ' glstex glsdefs';         # bib2gls
$clean_ext .= ' nlo nls';                 # nomencl
