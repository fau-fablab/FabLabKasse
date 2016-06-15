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

"""randomly built lists with randomness taken from random.choice()

.. WARNING:: not cryptographically secure!"""

def random_integer_list(random_generator, integer_range, number_of_elements):
    """ return a list of length number_of_elements
    with elements in the range integer_range[0] <= element <= integer_range[1]

    :param random.Random random_generator: RNG instance
    :param (int, int) integer_range: range (min, max) -- ends are included
    :param int number_of_elements: length of resulting list"""
    my_list = []
    for _ in range(number_of_elements):
        my_list.append(random_generator.randint(integer_range[0], integer_range[1]))
    return my_list

def random_choice_list(random_generator, possible_elements, number_of_elements):
    """return a random list with len(list)==number_of_elements,
    list[i] in possible_elements (duplicates are possible)

    :param random.Random random_generator: RNG instance
    :param list possible_elements: list elements to choose from
    :param int number_of_elements: length of resulting list"""
    ret = []
    for _ in range(number_of_elements):
        ret.append(random_generator.choice(possible_elements))
    return ret