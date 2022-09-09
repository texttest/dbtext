#!/usr/bin/env python

f = "C:\Users\Administrator\texttesttmp\birds.08Sep183642.1436\birds\MSSQL\classic_row_data\EmptyObservations\stats.birds"
import pstats
from pstats import SortKey
p = pstats.Stats(f)
p.strip_dirs().sort_stats(SortKey.NAME).print_stats()


