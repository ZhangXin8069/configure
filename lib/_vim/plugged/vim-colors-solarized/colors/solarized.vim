" solarized — precision colors for machines and people
" https://ethanschoonover.com/solarized
"
" Author: Ethan Schoonover
" Colorscheme: solarized dark (background = base03 #002b36)

set background=dark
highlight clear
if exists("syntax_on")
    syntax reset
endif
let g:colors_name = "solarized"

" Palette — each entry: [gui_hex, cterm_number]
" base03 #002b36 | base02 #073642 | base01 #586e75 | base00 #657b83
" base0  #839496 | base1  #93a1a1 | base2  #eee8d5 | base3  #fdf6e3
" yellow #b58900 | orange #cb4b16 | red    #dc322f | magenta #d33682
" violet #6c71c4 | blue   #268bd2 | cyan   #2aa198 | green   #859900

let s:pal = {
    \ 'base03':  ['#002b36', 234],
    \ 'base02':  ['#073642', 235],
    \ 'base01':  ['#586e75', 240],
    \ 'base00':  ['#657b83', 241],
    \ 'base0':   ['#839496', 244],
    \ 'base1':   ['#93a1a1', 245],
    \ 'base2':   ['#eee8d5', 187],
    \ 'base3':   ['#fdf6e3', 230],
    \ 'yellow':  ['#b58900', 136],
    \ 'orange':  ['#cb4b16', 166],
    \ 'red':     ['#dc322f', 160],
    \ 'magenta': ['#d33682', 125],
    \ 'violet':  ['#6c71c4', 61],
    \ 'blue':    ['#268bd2', 33],
    \ 'cyan':    ['#2aa198', 37],
    \ 'green':   ['#859900', 64],
    \ }

function! s:HL(group, fg_name, bg_name, attr)
    let l:guifg   = 'NONE'
    let l:guibg   = 'NONE'
    let l:ctermfg = 'NONE'
    let l:ctermbg = 'NONE'
    if a:fg_name != ''
        let l:guifg   = s:pal[a:fg_name][0]
        let l:ctermfg = s:pal[a:fg_name][1]
    endif
    if a:bg_name != ''
        let l:guibg   = s:pal[a:bg_name][0]
        let l:ctermbg = s:pal[a:bg_name][1]
    endif
    let l:attr = a:attr != '' ? a:attr : 'NONE'
    exec 'highlight ' . a:group
        \ . ' guifg='   . l:guifg
        \ . ' guibg='   . l:guibg
        \ . ' ctermfg=' . l:ctermfg
        \ . ' ctermbg=' . l:ctermbg
        \ . ' gui='     . l:attr
        \ . ' cterm='   . l:attr
endfunction

" Background / foreground
call s:HL('Normal',        'base0',  'base03',  '')
call s:HL('Cursor',        'base03', 'base0',   '')
call s:HL('CursorLine',    '',       'base02',  'NONE')
call s:HL('CursorLineNr',  'blue',   'base02',  'NONE')
call s:HL('CursorColumn',  '',       'base02',  'NONE')
call s:HL('ColorColumn',   '',       'base02',  'NONE')
call s:HL('LineNr',        'base01', 'base03',  '')
call s:HL('StatusLine',    'base3',  'base02',  'NONE')
call s:HL('StatusLineNC',  'base01', 'base03',  'NONE')
call s:HL('VertSplit',     'base02', 'base02',  'NONE')
call s:HL('Folded',        'base0',  'base02',  '')
call s:HL('FoldColumn',    'base0',  'base03',  '')
call s:HL('SignColumn',    'base0',  'base03',  '')
call s:HL('Visual',        '',       'base02',  'NONE')
call s:HL('Search',        'base03', 'yellow',  'NONE')
call s:HL('IncSearch',     'base03', 'orange',  'NONE')
call s:HL('Directory',     'blue',   '',        '')
call s:HL('MatchParen',    'base03', 'base01',  '')
call s:HL('Title',         'orange', '',        'bold')
call s:HL('MoreMsg',       'blue',   '',        '')
call s:HL('ModeMsg',       'blue',   '',        '')
call s:HL('Question',      'cyan',   '',        'bold')
call s:HL('WarningMsg',    'red',    '',        'bold')
call s:HL('ErrorMsg',      'base3',  'red',     'bold')
call s:HL('Error',         'red',    'base03',  'reverse')
call s:HL('Todo',          'magenta','base03',  'bold')
call s:HL('NonText',       'base02', '',        '')
call s:HL('SpecialKey',    'base02', '',        '')
call s:HL('Pmenu',         'base0',  'base02',  '')
call s:HL('PmenuSel',      'base03', 'blue',    '')
call s:HL('PmenuSbar',     '',       'base02',  '')
call s:HL('PmenuThumb',    'base0',  '',        '')
call s:HL('WildMenu',      'base03', 'blue',    '')
call s:HL('DiffAdd',       'base03', 'green',   '')
call s:HL('DiffDelete',    'base03', 'red',     '')
call s:HL('DiffChange',    'base03', 'yellow',  '')
call s:HL('DiffText',      'base03', 'blue',    '')
call s:HL('SpellBad',      'red',    'base03',  'undercurl')
call s:HL('SpellCap',      'violet', 'base03',  'undercurl')
call s:HL('SpellRare',     'cyan',   'base03',  'undercurl')
call s:HL('SpellLocal',    'yellow', 'base03',  'undercurl')

" Syntax
call s:HL('Comment',       'base01',  '',       'italic')
call s:HL('Constant',      'cyan',    '',       '')
call s:HL('String',        'cyan',    '',       '')
call s:HL('Character',     'cyan',    '',       '')
call s:HL('Number',        'cyan',    '',       '')
call s:HL('Boolean',       'cyan',    '',       '')
call s:HL('Float',         'cyan',    '',       '')
call s:HL('Identifier',    'blue',    '',       '')
call s:HL('Function',      'blue',    '',       '')
call s:HL('Statement',     'green',   '',       '')
call s:HL('Conditional',   'green',   '',       '')
call s:HL('Repeat',        'green',   '',       '')
call s:HL('Label',         'green',   '',       '')
call s:HL('Operator',      'green',   '',       '')
call s:HL('Keyword',       'green',   '',       '')
call s:HL('Exception',     'green',   '',       '')
call s:HL('PreProc',       'red',     '',       '')
call s:HL('Include',       'red',     '',       '')
call s:HL('Define',        'red',     '',       '')
call s:HL('Macro',         'red',     '',       '')
call s:HL('PreCondit',     'red',     '',       '')
call s:HL('Type',          'yellow',  '',       '')
call s:HL('StorageClass',  'yellow',  '',       '')
call s:HL('Structure',     'yellow',  '',       '')
call s:HL('Typedef',       'yellow',  '',       '')
call s:HL('Special',       'red',     '',       '')
call s:HL('SpecialChar',   'red',     '',       '')
call s:HL('Tag',           'red',     '',       '')
call s:HL('Delimiter',     'base0',   '',       '')
call s:HL('SpecialComment','base01',  '',       'italic')
call s:HL('Debug',         'red',     '',       '')
call s:HL('Underlined',    '',        '',       'underline')
call s:HL('Ignore',        'base03',  '',       '')

delfunction s:HL

let g:terminal_ansi_colors = [
    \ s:pal.base03[0],  s:pal.red[0],     s:pal.green[0],  s:pal.yellow[0],
    \ s:pal.blue[0],    s:pal.magenta[0], s:pal.cyan[0],   s:pal.base0[0],
    \ s:pal.base01[0],  s:pal.orange[0],  s:pal.green[0],  s:pal.yellow[0],
    \ s:pal.blue[0],    s:pal.violet[0],  s:pal.cyan[0],   s:pal.base3[0]
    \ ]
