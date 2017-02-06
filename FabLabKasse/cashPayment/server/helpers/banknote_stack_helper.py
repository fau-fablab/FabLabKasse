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

"""helper for stack-based banknote payout systems. see :class:`BanknoteStackHelper`"""

import copy
import random
import unittest
import FabLabKasse.libs.random_lists as random_lists

class BanknoteStackHelper(object):
    """
    helper class for stack-based banknote payout systems.
    Such a system has a stack of banknotes from which the top one can be

    - either paid out to the client (action "payout")

    - or be irrevocably put away into a cashbox (action "stack"),
      from where it cannot be retrieved again for payout.

    From the programmer's point of view, this stack is a list of banknotes,
    from which only the last one (stack.pop()) can be accessed.

    This class makes the relevant decisions whether to pay out or stack away the current note.
    It also offers a matching implementation for :meth:`FabLabKasse.cashPayment.server.CashServer.getCanPayout`

    :param accepted_rest: see :meth:`FabLabKasse.cashPayment.server.cashServer.CashServer.getCanPayout`
    """
    def __init__(self, accepted_rest):
        self.accepted_rest = accepted_rest

    def _would_stack_from_payout(self, payout_stack, requested_payout):
        """
        check if moving a note from the payout store away to the cashbox could be useful
        :param int requested_payout: remaining maximum payout amount
        :param list[int] payout_stack: list of notes, the currently accessible one *last*. This is the format returned by :meth:`:meth:`FabLabKasse.cashPayment.server.NV11.NV11Device.getpayout_stack`

        :returns:
            False if moving is certainly useless and should not be allowed by the device driver
            True if it might be helpful. The driver should do further checks if it is really necessary.
        :rtype: bool
        """
        if not payout_stack:
            # no notes to payout
            return False
        if requested_payout < min(payout_stack):
            # we only have too large notes
            return False
        if requested_payout < self.accepted_rest and requested_payout < min(payout_stack[-2:]):
            # for values smaller than the accepted rest, discard one note at maximum
            # this means that the last note or the one before need to be okay
            return False
        return True

    def _simulate_simple_payout(self, payout_stack, requested_payout):
        """
        how much would be paid out by a rather simple algorithm that, unlike _forced_stacking_is_helpful(), does not do extremely-forward-looking stackaways?

        algorithm:
         - payout whenever possible
         - if payout is not possible (current note too large),
           stack away the current note if it is helpful enough, otherwise stop.

        parameters: see _would_stack_from_payout()
        """
        simulated_payout = 0
        payout_stack = copy.copy(payout_stack)
        while payout_stack:
            if simulated_payout + payout_stack[-1] <= requested_payout:
                # would pay out note, if it is not too large
                simulated_payout += payout_stack[-1]
                # print(payout_stack[-1])
            elif self._would_stack_from_payout(payout_stack, requested_payout - simulated_payout):
                # would stack away the note
                pass
            else:
                break
            payout_stack.pop()
        return {"payout": simulated_payout, "storageRemaining": sum(payout_stack)}

    def _forced_stacking_is_helpful(self, payout_stack, requested_payout):
        """
        will the simple payout the algorithm from _simulate_simple_payout() yield better results when the current top note is stacked away instead of paid out, and the rest is paid out with the simple algorithm?

        Because this function is guaranteed to yield results at least as good as the simple (statless) algorithm, it may be (statelessly) applied for every step of payout without bad effects.
        This guarantee is tested in BanknoteStackHelperTester.unittest_payout_forced_stacking().

        example 1: better payout
            stack: top 5€, 10€, 50€, bottom.
            requested amount 60€
            -> best solution would be to NOT pay out the current 5€ note, although 5€ < 60€, but stack it away and pay out the 10€ note.
            otherwise the payout would fail after 15€.

        example 2: more remaining storage
            stack: top 5€, 10€, 5€, ... bottom.
            requested amount 10€.
            -> best solution would be to NOT pay out the current 5€ note, although 5€ < 10€, but stack it away and pay out the 10€ note.
            otherwise 5€ storage would have been wasted.

        :returns: True if stacking is recommended, even if the note could be paid out
        """
        result_with_stacking = self._simulate_simple_payout(payout_stack[:-1], requested_payout)
        result_without_stacking = self._simulate_simple_payout(payout_stack, requested_payout)
        # print("simulation: stacking={},
        # payout={}".format(result_with_stacking, result_without_stacking))

        # better payout: see example 1
        # better storageRemaining: see example 2
        return result_with_stacking["payout"] > result_without_stacking["payout"]  \
            or result_with_stacking["storageRemaining"] > result_without_stacking["storageRemaining"]

    def get_next_payout_action(self, payout_stack, requested_payout):
        """which action should be taken next?
        (see the documentation for BanknoteStackHelper for more context information)
        """
        if not payout_stack:
            return "stop"
        if self._forced_stacking_is_helpful(payout_stack, requested_payout) and self._would_stack_from_payout(payout_stack, requested_payout):
            return "stack"
        if payout_stack[-1] <= requested_payout:
            # would pay out note, if it is not too large
            return "payout"
        else:
            if self._would_stack_from_payout(payout_stack, requested_payout):
                return "stack"
            else:
                return "stop"

    def can_payout(self, payout_stack):
        """ implementation for CashServer.getCanPayout()"""
        if not payout_stack:
            # no notes available at all
            return self.accepted_rest

        if min(payout_stack) > self.accepted_rest + 1:
            # no small notes available
            return self.accepted_rest

        # for every amount, simulate a payout

        # why is this necessary?
        # look at this example: we have 1*20€ and 1*5€ stored. requested_value (maximum possible payout) = 40€, accepted rest = 9,99€.
        # this is enough for 20€, but not for 15€!
        # it is enough for 14,99 and every lower amount, so this should return
        # 1499 (or any lower value).

        requested_value = self.accepted_rest
        last_successful_request = 0
        while True:
            could_payout_sum = self._simulate_simple_payout(payout_stack, requested_value)["payout"]
            assert could_payout_sum <= requested_value  # otherwise would have paid ot more than requested!
            if could_payout_sum >= requested_value - self.accepted_rest:
                # enough can be paid
                last_successful_request = requested_value
                # go to the next value, but skip all that would already be satisfied by the current payout amount
                # e.g. the current request for 25€ resulted in a payout of 20.
                # that means, all requests for <= (20€ + accepted_rest) can also be satisfied.
                requested_value = could_payout_sum + self.accepted_rest + 1
                continue
            else:
                # cannot pay enough!
                return last_successful_request


class BanknoteStackHelperTester(BanknoteStackHelper):
    """unittest methods for BanknoteStackHelper"""

    @classmethod
    def get_random_payout_parameters(cls, random_generator, payout_stack=None, requested_payout=None):
        """determine parameters for payout_stack and requested_payout

        :param random.Random random_generator: RNG instance for calculating
            pseudorandom test parameters"""
        if payout_stack is None:
            payout_stack = random_lists.random_choice_list(
                random_generator,
                possible_elements=[500, 1000, 2000, 5000],
                number_of_elements=random.randint(1, 8))
        if requested_payout is None:
            requested_payout = random.randint(1, sum(payout_stack))
        assert 0 < requested_payout <= sum(payout_stack)
        return [payout_stack, requested_payout]

    def unittest_payout_forced_stacking(self, random_generator):
        """test one random set of parameters for BanknoteStackHelper._forced_stacking_is_helpful()

        :param random.Random random_generator: RNG instance for calculating
            pseudorandom test parameters
        :rtype: None
        :raise: AssertionError if the test failed"""
        [payout_stack, requested_payout] = self.get_random_payout_parameters(random_generator)

        origpayout_stack = copy.deepcopy(payout_stack)

        simulated_payout = 0
        while payout_stack:
            if self._forced_stacking_is_helpful(payout_stack, requested_payout):
                pass
                # print("extra stack away useful")
            if simulated_payout + payout_stack[-1] <= requested_payout:
                # would pay out note, if it is not too large
                simulated_payout += payout_stack[-1]
                # print(payout_stack[-1])
            elif self._would_stack_from_payout(payout_stack, requested_payout - simulated_payout):
                # would stack away the note
                # print("stack anyway.")
                pass
            else:
                break
            payout_stack.pop()
        payout_without_forced_stacking = self._simulate_simple_payout(
            origpayout_stack, requested_payout)
        assert simulated_payout >= payout_without_forced_stacking["payout"]
        assert sum(payout_stack) >= payout_without_forced_stacking["storageRemaining"]

    def unittest_payout(self, random_generator):
        """test one random set of parameters for BanknoteStackHelper.can_payout(), BanknoteStackHelper.get_next_payout_action()

        :param random.Random random_generator: RNG instance for calculating
            pseudorandom test parameters
        :rtype: None
        :raise: AssertionError if the test failed"""
        [payout_stack, requested_payout] = self.get_random_payout_parameters(random_generator)
        payout_stack_original = copy.deepcopy(payout_stack)  # for debugging
        payout_stack_original = payout_stack_original  # suppress unused-warning

        can_payout = self.can_payout(payout_stack)
        sum_paid_out = 0
        while True:
            action = self.get_next_payout_action(
                payout_stack, requested_payout - sum_paid_out)
            if action == "stop":
                break
            assert len(payout_stack) > 0
            current_note = payout_stack.pop()
            if action == "payout":
                sum_paid_out += current_note
        if requested_payout < self.accepted_rest:
            # requests below the accepted rest may be handled in any way
            # (Except paying out too much, which is checked far below)
            pass
        elif sum_paid_out < max(requested_payout - self.accepted_rest, 0):
            # if not enough was paid out, the payout stack must not contain
            # anything useful
            assert len(payout_stack) == 0 or \
                requested_payout - sum_paid_out < min(payout_stack)
            if requested_payout <  can_payout:
                assert False, "the request {0} was not greater than canPayout {1}, it must be satisfied at the given max. accepted rest of {2}, but only {3} was paid from stack {4}".format(requested_payout, can_payout, self.accepted_rest, sum_paid_out, payout_stack_original)
        assert sum_paid_out <= requested_payout  # did not pay out too much



class BanknoteStackHelperTest(unittest.TestCase):
    """Tests the banknote stack helper class"""

    def test_with_fixed_values(self):
        # test case (formerly a bug):
        # stack is 2x5€ 2x50€, accepted rest 34,32€
        # -> a request 44,32€ < x < 50€ cannot be satisfied,
        test = BanknoteStackHelper(3432)
        self.assertLessEqual(test.can_payout([500, 500, 5000, 5000]), 500+500+3432)
        test = BanknoteStackHelper(2167)
        self.assertLessEqual(test.can_payout([2000, 5000]), 2000+2167)


    def test_with_several_random_values(self):
        """unittest: calls several integrated functions of banknote stack helper as test with several random numbers"""
        seed = random.random()
        # for repeating a fixed test, override a seed value here:
        print("banknote_stack_helper random test using seed=" + repr(seed))
        random_generator = random.Random((seed,42))
        test = BanknoteStackHelperTester(2500)
        test.can_payout([5000, 10000, 10000, 2000])

        # edge cases: 10€ banknotes with 9.99 accepted rest -> works
        # 10€ notes with 9.98 accepted rest -> doesn't work
        test1 = BanknoteStackHelperTester(999)
        test2 = BanknoteStackHelperTester(998)

        for count in range(1, 10):
            notes = [1000] * count
            self.assertTrue(test1.can_payout(notes) >= 1000 * count)
            self.assertTrue(test2.can_payout(notes) <= 998)

        self.assertTrue(test1.can_payout([2000]) <= 999)
        self.assertTrue(test1.can_payout([1001]) <= 999)

        # test random values and, especially hard, accepted_rest=999
        for accepted_rest in random_lists.random_integer_list(random_generator, (1, 123456), 42) + [999] * 10:
            test = BanknoteStackHelperTester(accepted_rest)
            for _ in range(2345):
                test.unittest_payout(random_generator)
                test.unittest_payout_forced_stacking(random_generator)


if __name__ == "__main__":
    unittest.main()
