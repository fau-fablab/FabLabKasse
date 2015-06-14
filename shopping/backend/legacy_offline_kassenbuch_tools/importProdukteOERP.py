#!/usr/bin/env python
# -*- coding: utf-8 -*-

# SVG Templating System (C) Max Gaukler 2013
# unlimited usage allowed, see LICENSE file

# Dependencies

import sys, os
import oerplib
import locale
from ConfigParser import ConfigParser
import codecs


# switching to german:
locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
reload(sys).setdefaultencoding('UTF-8') # somehow doesn't work

if (sys.stdout.encoding != "UTF-8"):            
    print sys.stdout.encoding
    print >> sys.stderr, "please use a UTF-8 locale, e.g. LANG=en_US.UTF-8" 
    exit(1)

cfg = ConfigParser({'db_file': 'production.sqlite3', 'request_backup': 'off',
                    'cash': 'off', 'cash_manual': 'off', 'FAUcard': 'off', 'invoice': 'off'})
cfg.readfp(codecs.open('config.ini', 'r', 'utf8'))

oerp = oerplib.OERP(server=cfg.get('openerp', 'server'), protocol='xmlrpc+ssl',
                    database=cfg.get('openerp', 'database'), port=cfg.getint('openerp', 'port'),
                    version=cfg.get('openerp', 'version'))
user = oerp.login(user=cfg.get('openerp', 'user'), passwd=cfg.get('openerp', 'password'))

def str_to_int(s, fallback=None):
    try:
        return int(s)
    except ValueError:
        return fallback


class cache(object):
    def __init__(self, f):
        self.cache = {}
        self.f = f

    def __call__(self, *args, **kwargs):
        hash = str(args)+str(kwargs)
        
        if hash not in self.cache:
            ret = self.f(*args, **kwargs)
            self.cache[hash] = ret
        else:
            ret = self.cache[hash]
        
        return ret



@cache
def categ_id_to_list_of_names(c_id):
    categ = oerp.read('product.category', c_id, ['parent_id', 'name'], context=oerp.context)
    
    if categ['parent_id'] == False or \
           categ['parent_id'][0] == cfg.getint('openerp', 'base_category_id'):
        return [categ['name']]
    else:
        return categ_id_to_list_of_names(categ['parent_id'][0])+[categ['name']]
        

def importProdukteOERP(data):
    print "OERP Import"
    prod_ids = oerp.search('product.product', [('default_code', '!=', False)])
    print "reading {} products from OERP, this may take some minutes...".format(len(prod_ids))
    prods = oerp.read('product.product', prod_ids, ['code', 'name', 'uom_id', 'list_price', 'categ_id', 'active', 'sale_ok'],
        context=oerp.context)
    
    # Only consider things with numerical PLUs in code field
    prods = filter(lambda p: str_to_int(p['code']) is not None, prods)
    
    # which units are only possible in integer amounts? (e.g. pieces, pages of paper)
    integer_uoms = oerp.search('product.uom', [('rounding', '=', 1)])
    
    for p in prods:
        if p['list_price'] <= 0:
            # WORKAROUND: solange die Datenqualität so schlecht ist, werden Artikel mit Preis 0 erstmal ignoriert.
            continue
        if not p['active'] or not p['sale_ok']:
            continue
        p['code'] = int(p['code'])
        p['categ'] = categ_id_to_list_of_names(p['categ_id'][0])
        
        if p['categ'][0] not in data:
            data[p['categ'][0]] = []
        
        p['input_mode']='DECIMAL'
        if p['uom_id'][0] in integer_uoms:
            p['input_mode'] = 'INTEGER'
        data[p['categ'][0]].append(
            (p['code'], p['name'], p['uom_id'][1], p['list_price'], p['input_mode'], p['categ'][1:], []))

    return data


def saveToDir(data, outputdir):
    files_written = []
    for g in data.keys():
        filename = g.replace("/", "__") + ".txt"
        files_written.append(filename)
        print filename
        f = open(outputdir + filename, 'w')
        
        # In Datei schreiben
        def formatiereOutput(d):
            s='%04d;%s;%s;%s;%s;%s\n' % (d[0],  d[1],  d[2],  d[3], d[4], d[5])
            if d[6]:
                # weitere Verkaufseinheiten
                for einheit in d[6]:
                    s += '\t%s;%s;%s;%s\n' % einheit;
            return s
        
        for l in map(lambda d: formatiereOutput(d), data[g]):
            f.write(l.encode('utf-8'))
    
        f.close()
    for f in os.listdir(outputdir):
        if f.endswith(".txt") and f not in files_written:
            print "removing stale file {}".format(f)
            os.unlink(outputdir + f)

def main():    
    data = {}
    data = importProdukteOERP(data)
    outputdir = os.path.dirname(os.path.realpath(__file__))+'/../../../produkte/'
    
    saveToDir(data, outputdir)

if __name__ == '__main__':
    main()
