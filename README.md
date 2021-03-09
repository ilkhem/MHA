#+TITLE: Improved MHA

This repository contains an in improved implementation of the MHA algorithm by [https://arxiv.org/abs/1805.09567](Monti and Hyvärinen \(2018\)) which was used for brain age prediction in [https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0232296](Monti et al. \(2020\)).

There is a silent [./mha/legacy.py::""   "# BUG: this function changes the value of its input!!!!!](bug) in the original implementation, which has been fixed in the current implementation. Because of this, the output of the improved implementation differs from the original's.

The file `main.py` can be used to run simulations on toy data, and compare the new and legacy implementations.

Run for `N in 1 2 3 5 10` and `n in 10 25 50 100 150 500 1000 1500 2500`.
