# init
_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo 'HOME:'${_HOME}
_NAME=$(basename "$0")
name='test'
work_name="test"
tmp_name="tmp"
work_path=${_HOME}/${work_name}
tmp_path=${_HOME}/${tmp_name}
# mkdir
mkdir ${_HOME}/bin -p
mkdir ${_HOME}/include -p
mkdir ${_HOME}/lib -p
mkdir ${_HOME}/scripts -p
mkdir ${_HOME}/test -p
mkdir ${_HOME}/tmp -p
# source
source ${_HOME}/tmp/scripts.sh
# export
## zhangxin
# export TERM=xterm-256color
export PATH=$PATH:${_HOME}/bin
# export PATH=$PATH:${HOME}/.local/bin
# openmpi
# MPI_HOME=/usr/local/openmpi
# # export PATH=${MPI_HOME}/bin:$PATH
# # # export LD_LIBRARY_PATH=${MPI_HOME}/lib:$LD_LIBRARY_PATH
# # export MPI_INCLUDE_PATH=${MPI_HOME}/include:$MPI_INCLUDE_PATH
# export MANPATH=${MPI_HOME}/share/man:$MANPATH
# cuda
# CUDA_HOME=/usr/local/cuda
# export PATH=${CUDA_HOME}/bin:$PATH
# export LD_LIBRARY_PATH=${CUDA_HOME}/lib:$LD_LIBRARY_PATH
# export CUDA_INCLUDE_PATH=${CUDA_HOME}/include:$CUDA_INCLUDE_PATH
# export MANPATH=${CUDA_HOME}/share/man:$MANPATH
# alias
# alias noita="pushd ${HOME}/Game/Noita\ v20230311 && wine noita.exe && popd"
# alias dwarf="pushd ${HOME}/Game/Dwarf\ Fortress && wine Dwarf\ Fortress.exe && popd"
# alias rain="pushd ${HOME}/Game/Rain\ World\ v1.9.07b && wine RainWorld.exe && popd"
# alias oriwotw="pushd ${HOME}/Game/Ori\ and\ the\ Will\ of\ the\ Wisps && wine oriwotw.exe && popd"
# alias deadcells="pushd ${HOME}/Game/Dead\ Cells2 && wine deadcells.exe && popd"
# alias cchess="pushd ${HOME}/Package && wine ChineseChess.exe && popd"
# alias gchess="pushd ${HOME}/Package && wine GoChess.exe && popd"
# alias gomoku="pushd ${HOME}/Package && wine Gomoku.exe && popd"
# alias space="pushd ${HOME}/Package && wine SpaceSniffer.exe && popd"
# alias clash="pushd ${HOME}/Package/Clash\ for\ Windows && ./cfw --no-sandbox && popd"
# alias joplin="pushd ${HOME}/Package/Joplin && ./Joplin.AppImage --no-sandbox && popd"
# alias krita="pushd ${HOME}/Package/Krita && ./krita.appimage --no-sandbox && popd"
# alias onenote="pushd ${HOME}/Package/OneNote && ./onenote-desktop.AppImage --no-sandbox && popd"
# alias winrar="pushd ${HOME}/Package/WinRARPortable && wine WinRARPortable.exe && popd"
# alias matlab="pushd ${HOME}/Package/MATLAB/R2023b/bin && bash matlab && popd"
# alias -='cd -'
alias cchess="pushd ${_HOME}/lib/Package && wine ChineseChess.exe && popd"
alias gchess="pushd ${_HOME}/lib/Package && wine GoChess.exe && popd"
alias gomoku="pushd ${_HOME}/lib/Package && wine Gomoku.exe && popd"
alias space="pushd ${_HOME}/lib/Package && wine SpaceSniffer.exe && popd"
# alias qcu="conda activate qcu && cd ${HOME}/qcu"
# alias base="conda deactivate && cd ${HOME}"
alias ...=../..
alias ....=../../..
alias .....=../../../..
alias ......=../../../../..
alias 1='cd -1'
alias 2='cd -2'
alias 3='cd -3'
alias 4='cd -4'
alias 5='cd -5'
alias 6='cd -6'
alias 7='cd -7'
alias 8='cd -8'
alias 9='cd -9'
alias _='sudo '
alias dbl='docker build'
alias dcin='docker container inspect'
alias dcls='docker container ls'
alias dclsa='docker container ls -a'
alias dib='docker image build'
alias dii='docker image inspect'
alias dils='docker image ls'
alias dipru='docker image prune -a'
alias dipu='docker image push'
alias dirm='docker image rm'
alias dit='docker image tag'
alias dlo='docker container logs'
alias dnc='docker network create'
alias dncn='docker network connect'
alias dndcn='docker network disconnect'
alias dni='docker network inspect'
alias dnls='docker network ls'
alias dnrm='docker network rm'
alias dpo='docker container port'
alias dps='docker ps'
alias dpsa='docker ps -a'
alias dpu='docker pull'
alias dr='docker container run'
alias drit='docker container run -it'
alias drm='docker container rm'
alias 'drm!'='docker container rm -f'
alias drs='docker container restart'
alias dst='docker container start'
alias dsta='docker stop $(docker ps -q)'
alias dstp='docker container stop'
alias dtop='docker top'
alias dvi='docker volume inspect'
alias dvls='docker volume ls'
alias dvprune='docker volume prune'
alias dxc='docker container exec'
alias dxcit='docker container exec -it'
alias egrep='grep -E --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias fgrep='grep -F --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias g=git
alias ga='git add'
alias gaa='git add --all'
alias gam='git am'
alias gama='git am --abort'
alias gamc='git am --continue'
alias gams='git am --skip'
alias gamscp='git am --show-current-patch'
alias gap='git apply'
alias gapa='git add --patch'
alias gapt='git apply --3way'
alias gau='git add --update'
alias gav='git add --verbose'
alias gb='git branch'
alias gbD='git branch --delete --force'
alias gba='git branch --all'
alias gbd='git branch --delete'
alias gbg='LANG=C git branch -vv | grep ": gone\]"'
alias gbgD='LANG=C git branch --no-color -vv | grep ": gone\]" | cut -c 3- | awk '\''{print $1}'\'' | xargs git branch -D'
alias gbgd='LANG=C git branch --no-color -vv | grep ": gone\]" | cut -c 3- | awk '\''{print $1}'\'' | xargs git branch -d'
alias gbl='git blame -w'
alias gbm='git branch --move'
alias gbnm='git branch --no-merged'
alias gbr='git branch --remote'
alias gbs='git bisect'
alias gbsb='git bisect bad'
alias gbsg='git bisect good'
alias gbsn='git bisect new'
alias gbso='git bisect old'
alias gbsr='git bisect reset'
alias gbss='git bisect start'
alias gc='git commit --verbose'
alias 'gc!'='git commit --verbose --amend'
alias gcB='git checkout -B'
alias gca='git commit --verbose --all'
alias 'gca!'='git commit --verbose --all --amend'
alias gcam='git commit --all --message'
alias 'gcan!'='git commit --verbose --all --no-edit --amend'
alias 'gcann!'='git commit --verbose --all --date=now --no-edit --amend'
alias 'gcans!'='git commit --verbose --all --signoff --no-edit --amend'
alias gcas='git commit --all --signoff'
alias gcasm='git commit --all --signoff --message'
alias gcb='git checkout -b'
alias gcd='git checkout $(git_develop_branch)'
alias gcf='git config --list'
alias gcl='git clone --recurse-submodules'
alias gclean='git clean --interactive -d'
alias gclf='git clone --recursive --shallow-submodules --filter=blob:none --also-filter-submodules'
alias gcm='git checkout $(git_main_branch)'
alias gcmsg='git commit --message'
alias 'gcn!'='git commit --verbose --no-edit --amend'
alias gco='git checkout'
alias gcor='git checkout --recurse-submodules'
alias gcount='git shortlog --summary --numbered'
alias gcp='git cherry-pick'
alias gcpa='git cherry-pick --abort'
alias gcpc='git cherry-pick --continue'
alias gcs='git commit --gpg-sign'
alias gcsm='git commit --signoff --message'
alias gcss='git commit --gpg-sign --signoff'
alias gcssm='git commit --gpg-sign --signoff --message'
alias gd='git diff'
alias gdca='git diff --cached'
alias gdct='git describe --tags $(git rev-list --tags --max-count=1)'
alias gdcw='git diff --cached --word-diff'
alias gds='git diff --staged'
alias gdt='git diff-tree --no-commit-id --name-only -r'
alias gdup='git diff @{upstream}'
alias gdw='git diff --word-diff'
alias gf='git fetch'
alias gfa='git fetch --all --tags --prune --jobs=10'
alias gfg='git ls-files | grep'
alias gfo='git fetch origin'
alias gg='git gui citool'
alias gga='git gui citool --amend'
alias ggpull='git pull origin "$(git_current_branch)"'
alias ggpur=ggu
alias ggpush='git push origin "$(git_current_branch)"'
alias ggsup='git branch --set-upstream-to=origin/$(git_current_branch)'
alias ghh='git help'
alias gignore='git update-index --assume-unchanged'
alias gignored='git ls-files -v | grep "^[[:lower:]]"'
alias git-svn-dcommit-push='git svn dcommit && git push github $(git_main_branch):svntrunk'
alias gk='\gitk --all --branches &!'
alias gke='\gitk --all $(git log --walk-reflogs --pretty=%h) &!'
alias gl='git pull'
alias glg='git log --stat'
alias glgg='git log --graph'
alias glgga='git log --graph --decorate --all'
alias glgm='git log --graph --max-count=10'
alias glgp='git log --stat --patch'
alias glo='git log --oneline --decorate'
alias globurl='noglob urlglobber '
alias glod='git log --graph --pretty="%Cred%h%Creset -%C(auto)%d%Creset %s %Cgreen(%ad) %C(bold blue)<%an>%Creset"'
alias glods='git log --graph --pretty="%Cred%h%Creset -%C(auto)%d%Creset %s %Cgreen(%ad) %C(bold blue)<%an>%Creset" --date=short'
alias glog='git log --oneline --decorate --graph'
alias gloga='git log --oneline --decorate --graph --all'
alias glol='git log --graph --pretty="%Cred%h%Creset -%C(auto)%d%Creset %s %Cgreen(%ar) %C(bold blue)<%an>%Creset"'
alias glola='git log --graph --pretty="%Cred%h%Creset -%C(auto)%d%Creset %s %Cgreen(%ar) %C(bold blue)<%an>%Creset" --all'
alias glols='git log --graph --pretty="%Cred%h%Creset -%C(auto)%d%Creset %s %Cgreen(%ar) %C(bold blue)<%an>%Creset" --stat'
alias glp=_git_log_prettily
alias gluc='git pull upstream $(git_current_branch)'
alias glum='git pull upstream $(git_main_branch)'
alias gm='git merge'
alias gma='git merge --abort'
alias gmc='git merge --continue'
alias gmom='git merge origin/$(git_main_branch)'
alias gms='git merge --squash'
alias gmtl='git mergetool --no-prompt'
alias gmtlvim='git mergetool --no-prompt --tool=vimdiff'
alias gmum='git merge upstream/$(git_main_branch)'
alias gp='git push'
alias gpd='git push --dry-run'
alias gpf='git push --force-with-lease --force-if-includes'
alias 'gpf!'='git push --force'
alias gpoat='git push origin --all && git push origin --tags'
alias gpod='git push origin --delete'
alias gpr='git pull --rebase'
alias gpra='git pull --rebase --autostash'
alias gprav='git pull --rebase --autostash -v'
alias gpristine='git reset --hard && git clean --force -dfx'
alias gprom='git pull --rebase origin $(git_main_branch)'
alias gpromi='git pull --rebase=interactive origin $(git_main_branch)'
alias gprv='git pull --rebase -v'
alias gpsup='git push --set-upstream origin $(git_current_branch)'
alias gpsupf='git push --set-upstream origin $(git_current_branch) --force-with-lease --force-if-includes'
alias gpu='git push upstream'
alias gpv='git push --verbose'
alias gr='git remote'
alias gra='git remote add'
alias grb='git rebase'
alias grba='git rebase --abort'
alias grbc='git rebase --continue'
alias grbd='git rebase $(git_develop_branch)'
alias grbi='git rebase --interactive'
alias grbm='git rebase $(git_main_branch)'
alias grbo='git rebase --onto'
alias grbom='git rebase origin/$(git_main_branch)'
alias grbs='git rebase --skip'
alias grep='grep --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox}'
alias grev='git revert'
alias greva='git revert --abort'
alias grevc='git revert --continue'
alias grf='git reflog'
alias grh='git reset'
alias grhh='git reset --hard'
alias grhk='git reset --keep'
alias grhs='git reset --soft'
alias grm='git rm'
alias grmc='git rm --cached'
alias grmv='git remote rename'
alias groh='git reset origin/$(git_current_branch) --hard'
alias grrm='git remote remove'
alias grs='git restore'
alias grset='git remote set-url'
alias grss='git restore --source'
alias grst='git restore --staged'
alias grt='cd "$(git rev-parse --show-toplevel || echo .)"'
alias gru='git reset --'
alias grup='git remote update'
alias grv='git remote --verbose'
alias gsb='git status --short --branch'
alias gsd='git svn dcommit'
alias gsh='git show'
alias gsi='git submodule init'
alias gsps='git show --pretty=short --show-signature'
alias gsr='git svn rebase'
alias gss='git status --short'
alias gst='git status'
alias gsta='git stash push'
alias gstaa='git stash apply'
alias gstall='git stash --all'
alias gstc='git stash clear'
alias gstd='git stash drop'
alias gstl='git stash list'
alias gstp='git stash pop'
alias gsts='git stash show --patch'
alias gstu='gsta --include-untracked'
alias gsu='git submodule update'
alias gsw='git switch'
alias gswc='git switch --create'
alias gswd='git switch $(git_develop_branch)'
alias gswm='git switch $(git_main_branch)'
alias gta='git tag --annotate'
alias gtl='gtl(){ git tag --sort=-v:refname -n --list "${1}*" }; noglob gtl'
alias gts='git tag --sign'
alias gtv='git tag | sort -V'
alias gunignore='git update-index --no-assume-unchanged'
alias gunwip='git rev-list --max-count=1 --format="%s" HEAD | grep -q "\--wip--" && git reset HEAD~1'
alias gup=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gup%F{yellow}\' is a deprecated alias, using \'%F{green}gpr%F{yellow}\' instead.%f"\n    gpr'
alias gupa=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gupa%F{yellow}\' is a deprecated alias, using \'%F{green}gpra%F{yellow}\' instead.%f"\n    gpra'
alias gupav=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gupav%F{yellow}\' is a deprecated alias, using \'%F{green}gprav%F{yellow}\' instead.%f"\n    gprav'
alias gupom=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gupom%F{yellow}\' is a deprecated alias, using \'%F{green}gprom%F{yellow}\' instead.%f"\n    gprom'
alias gupomi=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gupomi%F{yellow}\' is a deprecated alias, using \'%F{green}gpromi%F{yellow}\' instead.%f"\n    gpromi'
alias gupv=$'\n    print -Pu2 "%F{yellow}[oh-my-zsh] \'%F{red}gupv%F{yellow}\' is a deprecated alias, using \'%F{green}gprv%F{yellow}\' instead.%f"\n    gprv'
alias gwch='git whatchanged -p --abbrev-commit --pretty=medium'
alias gwip='git add -A; git rm $(git ls-files --deleted) 2> /dev/null; git commit --no-verify --no-gpg-sign --message "--wip-- [skip ci]"'
alias gwipe='git reset --hard && git clean --force -df'
alias gwt='git worktree'
alias gwta='git worktree add'
alias gwtls='git worktree list'
alias gwtmv='git worktree move'
alias gwtrm='git worktree remove'
alias history=omz_history
alias l='ls -lah'
alias la='ls -lAh'
alias ll='ls -lh'
alias ls='ls --color=tty'
alias lsa='ls -lah'
alias md='mkdir -p'
# alias nvvp='nvvp -vm /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java'
alias ohmyzsh='mate ~/.oh-my-zsh'
# alias python=python3
alias rd=rmdir
alias which-command=whence
alias zshconfig='mate ~/.zshrc'
alias gsize='git count-objects -vH'
