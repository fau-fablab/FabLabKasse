A Brief History of Cash-Acceptance
==================================

Prelude
^^^^^^^

The FAU FabLab is a universitarian grassroot FabLab at the Univeristy of Erlangen-Nuremberg in Germany, run by volunteers but with partial initial funding through the university. Students and any interested party can come by and make use of the FabLab in their free time or for class work and research. Since the upkeep of machines and tools, as well as the needed materials are not financed by the university, users have to pay for usage.

First Act
^^^^^^^^^

With a total of 1291 individual products for sale, you can imagine how messy it gets to handle and supervise finances and operations. We started with hand-labeling all products and trust users to pay the right amount into an opened cash box. But how could we know if somebody would steal money from the lab?

Second Act
^^^^^^^^^^

Next, we added a handwritten cash journal and asked users to write down the paid amounts. But with this came extra work, since I had to copy that paper over to an excel sheet and check the sums, roughly twice a week. Obviously people made mistakes and payed a little more or less, but it always evened out over a couple of days and we did not notice any theft. But with 1.000+ products, how do we keep track of what is being sold, you might ask. We did not. You might also ask, did you not get tired of typewriting endless lists of numbers and counting cash? For sure I did!

Therefore, we started implementing a touchscreen-based sales-terminal, which would replace the handwritten lists and know about all the 1.000+ products. It took some time, lots of python code and caffeinated drinks, but finally we had it. No more typing, but still all the counting of coins and bills.

Third Act
^^^^^^^^^

As time progressed, we were quite happy by all the automated tabulation and statistics. Until we noticed that 100 Euros were missing... We never figured it out, so we must assume that it was stolen out of the open cash box. What to do?

Fourth Act
^^^^^^^^^^

We already had the basic software at hand, but we needed hardware. Hardware to discourage people from stealing. Since weaponizing our cash box would not have been in line with the safety aspects of the Fab Charter nor the UN Declaration of Human Rights, we needed to take a look at less drastic measures. With a FabLab at hand, we began designing and building a FabATM, or for long-word-loving-germans: ein Besucherabkassiermaschinenautomat. For real: it is called kassenterminal, which means payment terminal.

Sixth Act
^^^^^^^^^

We have built an open-soure point-of-sale terminal, which has been in everyday operation for almost a year. It counts coins, bills, returns change, prints official receipts and is completely capable of self-service. It tracks sales and will soon accept electronic payments and tell us what to restock. No more theft has been detected and endless hours of counting coins and typing numbers have been abolished.

If you are interested in not reenacting our story, have a look at the following GitHub-projects, which contain all the information necessary to build your own:

   * Software: https://github.com/fau-fablab/FabLabKasse
   * Wooden case: https://github.com/fau-fablab/kassenautomat.CAD
   * Interface circuit board: https://github.com/fau-fablab/kassenautomat.mdb-interface

The cash-devices we used (for counting, verifying and returning bills and coins) are connected via an industry-standard interface and can be replaced with other such devices. They can also be ignored, if the use of an open cash box or a drop-in-only cash box (without change) is to be used. The software is already equipped for this.
Have fun and keep your bean counters and bank accounts happy by using and helping in developing our automated cash system!
