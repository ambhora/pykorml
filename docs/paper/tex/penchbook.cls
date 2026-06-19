% ------------------------------------------------------------------------------
% SPDX-License-Identifier: CC-BY-4.0
% Copyright (C) 2024 Jayesh Badwaik <j.badwaik@fz-juelich.de>
% ------------------------------------------------------------------------------
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{penchbook}
\LoadClassWithOptions{scrbook}


\RequirePackage{penchcommon}

% --------------------------------------------------------------------------------------------------
% Configure ToC Tools
% --------------------------------------------------------------------------------------------------
\PassOptionsToClass{headings=optiontoheadandtoc}{scrbook}
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{2}

\RedeclareSectionCommand[tocnumwidth=2.0em]{part}
\RedeclareSectionCommand[tocindent=1em,tocnumwidth=2.0em]{chapter}
\RedeclareSectionCommand[tocindent=2.5em,tocnumwidth=2.0em]{section}
\RedeclareSectionCommand[tocindent=4.0em,tocnumwidth=3.0em]{subsection}


% --------------------------------------------------------------------------------------------------
% Configure Headers
% --------------------------------------------------------------------------------------------------
\RequirePackage[automark,autooneside=false]{scrlayer-scrpage}

\defpairofpagestyles{chapter}{
  \clearpairofpagestyles
  \cfoot{\rule[\baselineskip]{\textwidth}{0.1pt}}
  \ofoot{\pagemark}
}

\renewcommand*{\chapterpagestyle}{chapter}
\defpairofpagestyles{main}{
  \clearpairofpagestyles
  \cfoot{\rule[\baselineskip]{\textwidth}{0.1pt}}
  \chead{\rule[-\baselineskip]{\textwidth}{0.1pt}}
  \ofoot{\pagemark}
  \automark[section]{chapter}
  \lehead{\leftmark}
  \rohead{\rightmark}
}

% --------------------------------------------------------------------------------------------------
% Configure Chapter title
% --------------------------------------------------------------------------------------------------
% Set Font Size of Chapter Title Text
\addtokomafont{chapter}{
  \fontsize{1.8ex}{1.8ex}\selectfont
}

% Set Font Size of Chapter Number Text
\newkomafont{chapternumber}{
  \fontsize{5ex}{5ex}\selectfont
}

% Set Font Size of Chapter Name Text
\newkomafont{chaptername}{
  \itshape\rmfamily\normalsize
}

\makeatletter
\renewcommand{\chapterlinesformat}[3]{%
  \begin{minipage}{0.20\textwidth}
    \begin{center}
      #2
    \end{center}
  \end{minipage}
  ~
  \begin{minipage}[b]{0.79\textwidth}
    \linespread{1.5}\selectfont
    \begin{flushleft}
      #3
    \end{flushleft}
  \end{minipage}
}
\makeatother

% Set Chapter Formatting
\renewcommand\chapterformat{
  \parbox[b][8ex]{3em}{
    \centering{
      \usekomafont{chaptername}{\chaptername}
    }\\
    \vspace{0ex}
    \usekomafont{chapternumber}{\thechapter}
    \vfill
  }
  \rule[-0.5ex]{1pt}{10ex}
  \enskip
}

% --------------------------------------------------------------------------------------------------
% Indexing
% --------------------------------------------------------------------------------------------------

\RequirePackage[acronym,symbols,nogroupskip]{glossaries-extra}
\setabbreviationstyle[acronym]{long-short}
\RequirePackage{imakeidx}

