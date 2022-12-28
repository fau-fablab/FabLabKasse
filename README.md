# FabLabKasse
code climate: [![Code Climate](https://codeclimate.com/github/fau-fablab/FabLabKasse/badges/gpa.svg)](https://codeclimate.com/github/fau-fablab/FabLabKasse)

unittests: [![Build Status](https://travis-ci.org/fau-fablab/FabLabKasse.svg?branch=development)](https://travis-ci.org/fau-fablab/FabLabKasse)
[![codecov.io](https://codecov.io/github/fau-fablab/FabLabKasse/coverage.svg?branch=development)](https://codecov.io/github/fau-fablab/FabLabKasse?branch=development) (we are proudly untested [TM])

FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops



Please see https://fablabkasse.readthedocs.io for the documentation





# Getting started

Please checkout the repository recursively since it contains submodules:

`git clone --recursive git@github.com:fau-fablab/FabLabKasse.git`

If you want to test on a VM, take a look at [README_Vagrant.md](README_Vagrant.md) on how to automatically set up a Virtualbox VM for testing.

See [INSTALLING.md](INSTALLING.md) for detailed instructions on how to install the required dependencies. You can skip the configuration stuff for later.

Then, for the first try, you can just do:

`./run.py --example`


Have fun and give feedback!

# Testing features without real hardware

- receipt printing: run `./tools/dummy-printserver` to roughly see how a receipt printer's output would look. Please note that receipt printing is not yet implemented on all shopping backends, also not in the example config.

# Debugging

for a graphical winpdb debugger, start:
`./run.py --debug`
and click "continue" a few times

# Code style guide

All contributions should have a good coding style:

## Formatting

We use black for formatting.
You can use a dockerized black instance with the container_black.sh shell script. Use it as you would black:

```
# format everything
./container_black.sh .
```

The provided VS Code setting calls this script in order to make sure that you can format with the same version of black.
When updating the version, make sure that you change it in both the GitHub Workflow and the container script.

## Low level (formatting, docs)

- write reStructuredText formatted function docstrings, example:
```
def do_something(value):
    """
    do something magic with value

    :return: True if the sun shines tomorrow, False otherwise
    :rtype: bool
    :param value: your telephone number
    :type value: str
    """
```

- for the docstrings, use the type syntax as defined at https://www.jetbrains.com/pycharm/help/type-hinting-in-pycharm.html#d301935e18526
- custom __repr__() methods must return ASCII strings, not unicode objects. (OUTDATED - has changed with python3! TODO FIXME)

## High level (structure)

- Make your code modular, reusable and well-documented. Not only for others, but also for your future self.
- Use enough assertions in all code that has to do with money (payment, accounting, etc.).
- For signaling errors, prefer Exceptions to return codes.
- Avoid print! Use logging.info, logging.warning etc. because these are automatically saved to a logfile.
- Importing a file must not cause any side-effects. For scripts that should do something when called from the shell, you can use the following pattern:

```
def main():
    print "Hello, this is yourscript.py"
    do_something()

if __name__ == "__main__":
    main()

```

- Unittests must use the python unittest module so that they can be found by run_unittests.sh. Please see `FabLabKasse/example_unittest.py` for a working example.

# Contributing

- This project is available under GPLv3 (see file `LICENSE`)
- Follow the Code style guide
- Develop features in a separate branch, rebasing into logically divided commits is encouraged
- Please no fast-forward-merging (use `git merge --no-ff`, standard behaviour of Github pull requests)
- [This article](http://nvie.com/posts/a-successful-git-branching-model/) propagates a similar model
- You should add the following to your `.git/config` in order to support merging of the hypothesis-database:
```
[merge "hypothesisdb"]
  name = Hypothesis database files
  driver = python -m hypothesis.tools.mergedbs %O %A %B
```

# Commit messages

Please start your commit messages with FIX / ADD / IMPROVE / REFACTOR / DOC if it is possible and makes sense:

- new feature: `ADD clear-cart-button to user interface`
- improved existing feature: `IMPROVE payment_methods: add assertions and logging for payments`
- better code with the same behaviour: `REFACTOR usage of AbstractShoppingBackend.delete_current_order()`
- bugfix: `FIX crash when loading cart from app`
- only documentation changed: `DOC: better docstrings for AbstractShoppingBackend`
