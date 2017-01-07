from lib_d2infobot import D2BNClient
import sys

arv = sys.argv
usr = r'username'
if len(arv) == 2:
    usr = arv[1]

bot = D2BNClient("play.slashdiablo.net", 6112, usr)
bot.connect()
