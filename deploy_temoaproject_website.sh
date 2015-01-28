#!/bin/bash

set -e  # stop on error

REMOTE_SERVER='energym@temoaproject.org'
UPDDIR='.temoaproject.org-updating'
UPDPKG='.temoaproject.org-updating.tbz'
DELDIR='.temoaproject.org-deleting'
WEBDIR='temoaproject.org'

function usage () {
	BNAME=$(basename "$0")

	cat <<EOF
usage synopsis: $BNAME [--help|--debug]

This script is basically a codification of the steps to deploy to the website.
In other words, since most of the steps can be automated, this scripts does
that, also serving as a written form of the necessary actions to take and
providing some simple sanity checks.

This script also offers a reminder to seed a new torrent file for the
VirtualBox ova file that has become the Temoa Project's preferred method of
supporting Windows.
EOF

	exit 1
}

if [[ "$1" = "--help" ]]; then
	usage
fi

if [[ -e "./docs/" ]]; then
	cat <<EOF
Please remove the directory './docs/'.  This script will destroy anything in
that directory, so save any work you have in it and remove it.
EOF

	exit 1
fi

if [[ -z "$(which pv)" ]]; then
	cat <<EOF
Unable to find the 'pv' (Pipe Viewer) program.  Please install it before
rerunning this script.
EOF

	exit 1
fi

if [[ -z "$(which python)" ]]; then
	cat <<EOF
Unable to find Python.  Please install it, or appropriately modify
your path before continuing.
EOF

	exit 1
fi

if [[ -z "$(which sphinx-build)" ]]; then
	cat <<EOF
Unable to find sphinx-build utility.  Building the documentation requires
Sphinx.  Please install it before continuing.

Note that Sphinx is installable via pip:

    # install to system directories
    $ sudo pip install sphinx

Be sure to also install these packages from pip:

    sphinxcontrib-spelling
    sphinxcontrib-bibtex
    pyenchant

Also, if running Ubuntu, you may need to update the 'six' library:

    $ sudo pip install --upgrade six
EOF

	exit 1
fi

if [[ -z "$(which latex)" ]]; then
	cat <<EOF
Unable to find latex and associated libraries required to build the documentation. 
Please install it before continuing.

If using texlive, the following packages are required:

    texlive-latex-base
    texlive-latex-recommended
    texlive-fonts-recommended
    texlive-latex-extra
EOF

	exit 1
fi


git diff --quiet || (echo "Uncommitted changes in branch. Exiting ..." && exit 1)
git diff --cached --quiet || (echo "Uncommitted changes in index. Exiting ..." && exit 1)

TMP_DIR=$(mktemp -d --suffix='.DeployTemoaWebsite')

function cleanup () {
	# Called unless --debug passed as first argument to script

	\rm -rf "$TMP_DIR"
	\rm -rf /tmp/TemoaDocumentationBuild/
	git checkout --quiet temoaproject.org
	git checkout -- download/index.html  # undo MAGNET_URL
	\rm -rf ./docs/
	\rm -f ./download/temoa.py
	\rm -f ./download/TemoaDocumentation.pdf
	\rm -f ./download/example_data_sets.zip
}

if [[ "$1" != "--debug" ]]; then
	trap cleanup KILL TERM EXIT
else
	set -x
fi


echo -e "\nTesting ssh connection to $REMOTE_SERVER"
ssh -n $REMOTE_SERVER
ssh_error="$?"
if [[ "0" != "$ssh_error" ]]; then
	cat <<EOF
Unable to connect to '$REMOTE_SERVER' via ssh.  You will need to correct this
problem before continuing.
EOF

	exit $ssh_error
fi

echo -e "\nMaking temoa.py"

git checkout --quiet energysystem
./create_archive.sh
mv ./temoa.py "$TMP_DIR/"

echo "  Creating example_data_sets.zip"

cp -ra ./data_files/ "$TMP_DIR/example_data_sets/"
( cd "$TMP_DIR/"
  zip -qr9 example_data_sets.zip example_data_sets/
  rm -rf ./example_data_sets/
)

echo -e "\nMaking documentation"

( cd docs/
  make spelling
  echo -e "\n\nPotentially misspelled words:\n----------\n"
  cat /tmp/TemoaDocumentationBuild/spelling/output.txt
  echo
  read -p "Type 'continue' if there are no spelling issues: "  NO_SPELLING_ERRORS
  [[ "$NO_SPELLING_ERRORS" != "continue" ]] && exit 1
  make singlehtml
  make latexpdf
)

find . -name "*.pyc" -delete

echo -e "\nPiecing together website downloads ..."
git checkout --quiet temoaproject.org

mkdir -p ./docs/
mv /tmp/TemoaDocumentationBuild/singlehtml/* ./docs/
mv /tmp/TemoaDocumentationBuild/latex/TemoaProject.pdf ./download/TemoaDocumentation.pdf
mv "$TMP_DIR/"{temoa.py,example_data_sets.zip} ./download/

chmod 755 ./download/temoa.py
chmod 644 ./download/{example_data_sets.zip,TemoaDocumentation.pdf}

echo -e "\nUploading to website"
BYTES=$(tar --totals -cf - * .htaccess 2>&1 1> /dev/null | awk {'print $4'})

# We use this convoluted 'tar' pipeline to update the website, rather than a
# a more appropriate method (e.g., rsync), so that we can approach atomicity.
# That is, since our group may update the Temoa website from our respective
# homes, let's try to ensure that the update happens ... or it doesn't.  What we
# don't want, is half an update, and then our internet connection dies (for
# whatever reason).
tar -cf - * .htaccess | pv -s "$BYTES" | bzip2 --best | ssh "$REMOTE_SERVER" "cat > '$UPDPKG'" && \
  ssh "$REMOTE_SERVER" "rm -rf '$UPDDIR' && mkdir '$UPDDIR' && (cd '$UPDDIR'; tar -xf ../'$UPDPKG') && \
   mv '$WEBDIR' '$DELDIR' && mv '$UPDDIR' '$WEBDIR' && rm -rf '$DELDIR' '$UPDPKG'"

