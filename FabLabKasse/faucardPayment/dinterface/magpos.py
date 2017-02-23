#!/usr/bin/env python
"""
pymagpos -- MagnaCarta POS protocol (minimal robust implementation)
"""

import serial
import codes
import logging
import time

class MagposError(Exception):
    """ Base Exception Class for this Module """
    pass


class ResponseError(MagposError):
    """
    ResponseError occur when the response to a command does not match the command's OK signal.
    """
    def __init__(self, function, code):
        self.code = code
        self.function = function
        self.response = [code]

    def store_rawdata(self, response):
        """ Stores the raw response for evaluation purpose """
        self.raw = response

    def read_rawdata(self):
        """
        Returns the raw response data
        :return: Raw response data
        :rtype: list of ints
        """
        return self.raw


    def __str__(self):
        return ("[{0}] Unintended response received:{1}".format(self.function,
                codes.desc.setdefault(self.code, self.code)))


class TransactionError(MagposError):
    """
    TransactionError occur when the amount that has been decreased does not match the given amount
    """
    def __init__(self, card, old, new, amount):
        self.card = card
        self.old = float(old)/100
        self.new = float(new)/100
        self.amount = float(amount)/100

    def __str__(self):
        return "Difference in balance does not match the amount that should have been decreased.\
               \nCard:{0}\t Amount:{1:.2f}\nOld:{2:.2f}\tNew:{3:.2f}"\
                .format(self.card, self.amount, self.old, self.new)


class ConnectionTimeoutError(MagposError):
    """
    ConnectionTimeoutError occur, when the connection between the USB/RS232 reader and the MagnaBox is broken
    and/or the MagnaBox does not send a response message.
    """
    def __init__(self):
        pass

    def __str__(self):
        return ("Serial connection to MagnaBox timed out (did not send command?)")


class MagPOS:
    """
    MagPos Class implements functions to access payment features of the MagnaCarta-Security and Payment-System
    """
    def __init__(self, device):
        """
        Initializes the serial port communication on the given device port
        :param device: serial port name
        :type device: str
        """
        pass


    def start_connection(self, retries=5):
        """
        Initializes the connection
        :return: True if connection successful, False otherwise
        :rtype: bool
        :param retries: Max. Attempts to accomplish connection, Default value is 5
        :type retries: int
        """
        raise NotImplementedError()

    def card_on_reader(self):
        """
        Checks if there is a card on the reader
        :return: True if card on reader, False if not
        :rtype: bool
        """
        raise NotImplementedError()

    def set_display_mode(self, mode = 0, amount=0):
        """
        Sets the display configuration
        :return: True on success, False otherwise
        :rtype: bool
        :param mode: Config
        :type mode: int
        :param amonunt: (Optional) Amount the is asked for on display
        :type amount: int
        """
        raise NotImplementedError()

    def get_last_transaction_result(self):
        """
        Retrieves the details of last unacknowledged transaction
        :return: Returns List of relevant data: status code, card number and amount
        :rtype: list[int,int,int]
        """
        raise NotImplementedError()

    def response_ack(self):
        """
        Sends an acknowledge-signal to the MagaBox
        """
        raise NotImplementedError()


    def decrease_card_balance_and_token(self, amount, card_number=0, token_index=0):
        """
        Gives command to decrease balance by amount
        :return: Returns list of retrieved data: card number, old balance, new balance, token id
        :rtype: list[int,int,int,int]
        :param amount: Amount in Cents the card balance shall be decreased
        :type amount: int
        :param card_number: (Optional) sets the card number from which balance should be decreased
        :type card_number: int
        :param token_index: (Optional) sets token id which should be decreased by 1
        :type token_index: int
        """
        raise NotImplementedError()

    def get_long_card_number_and_balance(self):
        """
        Retrieves the card number and balance of the card on card reader
        :return: Returns list containing the response data from MagnaBox: card number and balance
        :rtype: list[int]
        """
        raise NotImplementedError()

    def close(self):
        """ Closes serial connection to MagnaBox. Needed to release the serial port for further transactions."""
        raise NotImplementedError()


if __name__ == '__main__':
    pos = MagPOS(device='/dev/ttyUSB0')
    pos.start_connection()
