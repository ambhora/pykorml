% --------------------------------------------------------------------------------------------------
% SPDX-License-Identifier: Apache-2.0
% Copyright (C) 2024 Jayesh Badwaik <jayesh@badwaik.dev>
% --------------------------------------------------------------------------------------------------

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{penchbeamer}
\RequirePackage[dvipsnames]{xcolor}
\LoadClassWithOptions{beamer}

\renewcommand*\insertshorttitle[1][]{%
  \beamer@setupshort{#1}%
  \let\thanks=\@gobble%
  \ifnum\c@page=1%
    \beamer@insertshort{\beamer@shorttitle}
  \else%
    \beamer@insertshort{\beamer@shorttitle}%
\fi}



%--------------------------------------------------------------------------------------------------
% Language and Font Support
% --------------------------------------------------------------------------------------------------
\RequirePackage{fontspec}
\RequirePackage{microtype}
\PassOptionsToPackage{final}{microtype}
\RequirePackage{unicode-math}

\setmainfont[Ligatures=TeXOff,ItalicFont={Linux Libertine O Italic}]{Alegreya}
\setsansfont{Alegreya Sans}
%\setmathfont[math-style=upright,Scale=MatchLowercase]{Latin Modern Math}
\setmathfont[Scale=MatchLowercase]{Latin Modern Math}

\setmathfont[range={bb},Scale=MatchLowercase]{TeX Gyre Pagella Math}
\setmathfont[range={scr,bfscr},Scale=MatchLowercase]{Tex Gyre Bonum Math}
\setmathfont[range=\setminus,Scale=MatchLowercase]{XITS Math}
\linespread{1.2}

\RequirePackage{polyglossia}
\setmainlanguage{english}
\RequirePackage{csquotes}
\RequirePackage{penchmathsym}
\RequirePackage{penchmath}
\RequirePackage{setspace}
\RequirePackage{enumitem}

%--------------------------------------------------------------------------------------------------
% Footer
% --------------------------------------------------------------------------------------------------
\makeatother
\setbeamertemplate{footline}
{
  \leavevmode
  \hbox{
    \begin{beamercolorbox}[
        wd=.20\paperwidth,
        ht=3ex,
        dp=1ex,
        center
      ]
      {author in head/foot,white}%
      \usebeamerfont{author in head/foot}
      \insertshortauthor
    \end{beamercolorbox}
    \begin{beamercolorbox}
      [wd=.34\paperwidth,ht=3ex,dp=1ex,center]
      {title in head/foot,white}
      \usebeamerfont{title in head/foot}
      \insertshorttitle
    \end{beamercolorbox}
    \begin{beamercolorbox}[wd=.25\paperwidth,ht=3ex,dp=1ex,center]{author in
      head/foot,white}
      \usebeamerfont{title in head/foot}
     \insertshortinstitute
    \end{beamercolorbox}
    \begin{beamercolorbox}[wd=.15\paperwidth,ht=3ex,dp=1ex,right]
      {author in head/foot, white}
      \insertframenumber{} / \inserttotalframenumber\hspace*{1ex}
    \end{beamercolorbox}
  }
  \vskip0pt%
}
\makeatletter


% Disable Navigation Symbols
\beamertemplatenavigationsymbolsempty


% --------------------------------------------------------------------------------------------------
%  Hyperref Support with Colored Links
% --------------------------------------------------------------------------------------------------


\PassOptionsToPackage{
  hypertexnames=true,
  plainpages=false,
  pdfpagelabels,
  pagebackref,
}
{hyperref}

\providecommand{\penchurlcolor}{Sepia}
\providecommand{\penchlinkcolor}{MidnightBlue}
\providecommand{\penchcitecolor}{ForestGreen}

\hypersetup{
  colorlinks=true,
  urlcolor=\penchurlcolor,
  linkcolor=\penchlinkcolor,
  citecolor=\penchcitecolor,
}

\PassOptionsToPackage{
  hypertexnames=true,
  plainpages=false,
  pdfpagelabels,
  pagebackref,
}
{hyperref}

\providecommand{\penchurlcolor}{Sepia}
\providecommand{\penchlinkcolor}{MidnightBlue}
\providecommand{\penchcitecolor}{ForestGreen}

\hypersetup{
  colorlinks=true,
  urlcolor=\penchurlcolor,
  linkcolor=\penchlinkcolor,
  citecolor=\penchcitecolor,
}
