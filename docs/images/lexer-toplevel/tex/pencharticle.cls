% ------------------------------------------------------------------------------
% SPDX-License-Identifier: CC-BY-4.0
% Copyright (C) 2024 Jayesh Badwaik <j.badwaik@fz-juelich.de>
% ------------------------------------------------------------------------------
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{pencharticle}
\LoadClassWithOptions{scrartcl}

\RequirePackage{penchcommon}

% --------------------------------------------------------------------------------------------------
% Configure ToC Tools
% --------------------------------------------------------------------------------------------------
\PassOptionsToClass{headings=optiontoheadandtoc}{scrartcl}
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{2}

\RedeclareSectionCommand[tocnumwidth=2.0em]{part}
\RedeclareSectionCommand[tocindent=1.0em,tocnumwidth=2.0em]{section}
\RedeclareSectionCommand[tocindent=2.5em,tocnumwidth=2.5em]{subsection}

% --------------------------------------------------------------------------------------------------
% Configure Headers
% --------------------------------------------------------------------------------------------------
\RequirePackage[automark,autooneside=false]{scrlayer-scrpage}
\defpairofpagestyles{title}{
  \clearpairofpagestyles
  \cfoot{\rule[\baselineskip]{\textwidth}{0.1pt}}
  \ofoot{\pagemark}
}

\defpairofpagestyles{main}{
  \clearpairofpagestyles
  \cfoot{\rule[\baselineskip]{\textwidth}{0.1pt}}
  \chead{\rule[-\baselineskip]{\textwidth}{0.1pt}}
  \automark[subsection]{section}
  \ofoot{\pagemark}
  \ihead{\leftmark}
  \ohead{\Ifstr{\leftmark}{\rightmark}{}{\rightmark}}
}

\renewcommand*{\titlepagestyle}{title}

% --------------------------------------------------------------------------------------------------
% Configure Part Titles to be on a Separate Page
% --------------------------------------------------------------------------------------------------
\renewcommand\partheadstartvskip{\clearpage\null\vfil}
\renewcommand\partheadmidvskip{\par\nobreak\vskip 20pt\thispagestyle{empty}}
\renewcommand\partheadendvskip{\vfil\clearpage}
\renewcommand\raggedpart{\centering}
