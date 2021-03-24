function venv {
  if [ ! -d venv ]; then
    python3.9 -m venv venv
    . venv/bin/activate
    pip install -U pip setuptools wheel &> /dev/null
  else
    . venv/bin/activate
  fi
}
export -f venv

function please {
  sudo "$@"
}
export -f please

function yoink {
  git pull "$@"
}
export -f yoink

function yeet {
  git push "$@"
}
export -f yeet

function gitpush {
  git commit -a -m "$*"
  git push
}
export -f gitpush
alias gp=gitpush

