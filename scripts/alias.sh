function venv {
  python3.9 -m venv venv
  . venv/bin/activate
  pip install -U pip setuptools wheel &> /dev/null
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
