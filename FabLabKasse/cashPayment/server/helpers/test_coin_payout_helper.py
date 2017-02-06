#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# (C) 2015 Max Gaukler <development@maxgaukler.de>

#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  The text of the license conditions can be read at
#  <http://www.gnu.org/licenses/>.

"""tests for :mod:`coin_payout_helper`"""

import unittest

from hypothesis import strategies as st
from hypothesis import example, given, settings
from hypothesis.strategies import composite

import FabLabKasse.cashPayment.server.helpers.coin_payout_helper as coin_payout_helper


def simulate_payout(coins, requested):
    """
    get payout amount for a very simple simulated payout strategy
    ('greedy strategy', just pay out largest coins first, without 'coin splitting' to get rid of smaller ones)

    :type coins: list[(int, int)]
    :param coins: see :meth:`coin_payout_helper.get_possible_payout`
    :param int requested: requested amount
    """
    paid_out = 0
    for (value, count) in coins:
        # the // floor division operator from __future__ is used here for clarity
        payout_count = min([count, (requested - paid_out) // value])
        paid_out += payout_count * value
    return paid_out

@composite
def st_coins(draw):
    """ generator for random coin status """
    st_usual_denominations = st.sets(st.sampled_from([200, 100, 50, 20, 10, 5, 2, 1]))
    st_strange_denominations_and_duplicates = st.lists(st.integers(1, 200), average_size=8)
    coin_values = draw(st.one_of(st_usual_denominations, st_strange_denominations_and_duplicates))
    # sort descending by coin value, and convert to list
    coin_values = sorted(coin_values, reverse=True)
    coin_list = [(value, draw(st.integers(min_value=0, max_value=10))) for value in coin_values]
    return coin_list

class CoinPayoutHelperTestcase(unittest.TestCase):
    """ Tests for :mod:`coin_payout_helper`"""
    @given(st_coins(), st.floats(0, 1), st.floats(0, 1), settings=settings(max_examples=1000))
    # the following two fixed testcases are already enough for full code coverage
    @example([], 1, .2)
    @example([(100, 1), (50, 2), (20, 3), (10, 1), (5, 0), (2, 0), (1, 0)], 1, 0.01)
    # another side-case: all zeroes
    @example([(100, 0), (50, 0), (20, 0), (10, 0), (5, 0), (2, 0), (1, 0)], 1, .2)
    def test_get_possible_payout(self, coins, requested_fraction, coin_limit_fraction):
        """ test :meth:`coin_payout_helper.get_possible_payout()` for a given state of available coins"""
        total = sum([value * count for (value, count) in coins])
        num_coins = sum([count for (value, count) in coins])
        (payout_infinite_coin_number, allowed_remaining) = coin_payout_helper.get_possible_payout(coins, max_number_of_coins=int(1e9))
        # print coins, total, (payout_infinite_coin_number, allowed_remaining)
        # the limit on the number of coins is not strictly guaranteed, so it isn't tested here.
        (payout_limited_coin_number, _) = coin_payout_helper.get_possible_payout(coins, max_number_of_coins=round(coin_limit_fraction * (num_coins + 20)))

        self.assertGreaterEqual(payout_limited_coin_number, 0)
        self.assertGreaterEqual(payout_infinite_coin_number, 0)
        self.assertLessEqual(payout_limited_coin_number, payout_infinite_coin_number)
        self.assertLessEqual(payout_infinite_coin_number, total)

        # pick request, simulate payout
        requested = round(requested_fraction * total)
        paid_out = simulate_payout(coins, requested)
        self.assertLessEqual(paid_out, requested)
        if requested > payout_infinite_coin_number:
            # requested too much, only the maximum is guaranteed
            self.assertGreaterEqual(paid_out, payout_infinite_coin_number - allowed_remaining)
        else:
            self.assertGreaterEqual(paid_out, requested - allowed_remaining)

if __name__ == "__main__":
    unittest.main()
