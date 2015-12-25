#!/usr/bin/env python2.7
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

"""helper functions for multi-tube coin dispensers"""


def get_possible_payout(coins, max_number_of_coins=15):
    """
    get possible amount of payout and remaining rest

    This implementation returns a lower bound. This means that the theoretical
    maximum possible amount can be higher (and will be often).

    :type coins: list[(int, int)]
    :param coins:
        list of tuples ``(value, count)``, sorted descending by value.
        The function still works if a value occurs twice (e.g. if you have a
        dispenser with two separate tubes for 1€ coins).
    :param int max_number_of_coins:
        approximate upper limit for the number of coins -
        this limits the reporting of the maximum possible amount of payout,
        so that a device won't say it is able to pay out 50€,
        if that is only possible with 500x 0,10€ coins.

        Please note that if you limit this too much, the user will be warned
        that there is not enough change money. Some amount is necessary,
        especially in cooperation with other devices (e.g. banknotes + coins).
    :return: as defined by :meth:`FabLabKasse.cashPayment.server.getCanPayout`
    """
    def is_sorted(iterable, reverse=False):
        """
        check if a list is sorted
        :param list iterable: list of values
        :param reverse: check for reverse sorted
        :rtype: bool
        """
        return sorted(iterable, reverse=reverse) == iterable
    assert is_sorted([value for (value, count) in coins], reverse=True), \
        "Coins must be sorted descending by value"
    total_amount = 0
    previous_coin_value = None

    # go through the coins from large to small
    for (value, count) in coins:
        assert isinstance(value, int)
        assert isinstance(count, int)

        if previous_coin_value is None:
            # first run of the loop
            previous_coin_value = 0
        else:
            if previous_coin_value % value != 0:
                # the new coin value is not a proper fraction (e.g. 1/5) of the
                # old coin value, so "splitting" (e.g. 50c -> 5x10c) is not
                # possible
                continue
            if count * value < previous_coin_value:
                # we dont have enough of this coin to "split" one previous coin
                continue

        # "split up" the previous coin, and add the remaining rest to to the
        # possible total amount
        total_amount += count * value - previous_coin_value
        previous_coin_value = value

    if previous_coin_value is None:
        return [0, 0]

    # limit total_amount to a practical maximum:
    # starting with the highest coin value, pay out (simulated) as much as
    # possible, until the maximum number of coins is reached.
    # This is the maximum useful payout amount, because paying out more
    # will require more coins.
    coins_allowed_remaining = max_number_of_coins
    maximum_useful_payout = 0
    for (value, count) in coins:
        if count > coins_allowed_remaining:
            count = coins_allowed_remaining
        coins_allowed_remaining -= count
        maximum_useful_payout += count * value

    if total_amount > maximum_useful_payout:
        total_amount = maximum_useful_payout

    return [total_amount, previous_coin_value]
