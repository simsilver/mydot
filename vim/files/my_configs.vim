set nu rnu
set noet
set wic
set formatoptions=tcqmM
set tw=80

if executable('rg')
	let g:ackprg = 'rg --vimgrep'
endif

let g:ale_virtualtext_cursor = 'all'
