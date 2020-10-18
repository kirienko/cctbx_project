from __future__ import absolute_import, division, print_function
import time
import mmtbx.model
import iotbx.pdb
from mmtbx.hydrogens import reduce
from libtbx.utils import null_out
from libtbx.test_utils import approx_equal


def run():
  correct_H_position_with_cdl()
  snippet_with_clashing_H()
  multi_model()
  normal_and_modified_nucleic_acid()


def compare_models(pdb_str,
                   contains     = None,
                   not_contains = None,
                   number_h     = None):
  #
  pdb_inp = iotbx.pdb.input(lines=pdb_str.split("\n"), source_info=None)
  model_initial = mmtbx.model.manager(model_input = pdb_inp,
                                      log         = null_out())
  hd_sel_initial = model_initial.get_hd_selection()
  number_h_expected = hd_sel_initial.count(True)


  model_without_h = model_initial.select(~hd_sel_initial)
  hd_sel_without_h = model_without_h.get_hd_selection()
  assert (hd_sel_without_h is not None)
  assert (hd_sel_without_h.count(True) == 0)

  model_h_added = reduce.add(model = model_without_h)
  hd_sel_h_added = model_h_added.get_hd_selection()

  ph_initial = model_initial.get_hierarchy()
  h_atoms_initial = ph_initial.select(hd_sel_initial).atoms()
  h_names_initial = list(h_atoms_initial.extract_name())
  ph_h_added = model_h_added.get_hierarchy()
  assert ph_initial.is_similar_hierarchy(other=ph_h_added)

  number_h_added = hd_sel_h_added.count(True)
  if number_h:
    assert(number_h == number_h_added)

  h_atoms_added = ph_h_added.select(hd_sel_h_added).atoms()
  h_names_added = list(h_atoms_added.extract_name())

  if not_contains:
    assert (not_contains not in h_names_added)

  if contains:
    assert (contains in h_names_added)

  sc_h_initial = model_initial.select(hd_sel_initial).get_sites_cart()
  sc_h_added = model_h_added.select(hd_sel_h_added).get_sites_cart()

  d1 = {h_names_initial[i]: sc_h_initial[i] for i in range(len(h_names_initial))}
  d2 = {h_names_added[i]: sc_h_added[i] for i in range(len(h_names_added))}

  for name, sc in d2.items():
    assert(name in d1)
    assert approx_equal(sc, d1[name], 0.01)


def correct_H_position_with_cdl():
  compare_models(pdb_str = pdb_str_1)


def snippet_with_clashing_H():
  '''
  This is an example for a file that fails with REDUCE.

  The NZ atom of Lys 246 and the C5 atom of Tam 2 are extremely close together,
  which seems to give Reduce a problem.

  Removing either Lys 246 NZ, or TAM 2 C5, or both of Lys 246 HZ1 and HZ3 will
  allow Reduce to run to completion and produce a usable result.
  However, Lys 246 HZ1 and HZ3 will not be added back by Reduce.
  '''
  compare_models(pdb_str = pdb_str_2)


def multi_model():
  '''
    Test if multi-model file is supported
  '''
  compare_models(pdb_str = pdb_str_3)


def normal_and_modified_nucleic_acid():
  compare_models(pdb_str = pdb_str_4)


pdb_str_1 = """
CRYST1   72.240   72.010   86.990  90.00  90.00  90.00 P 21 21 21
ATOM      1  N   PRO H  14      52.628 -74.147  33.427  1.00 20.43           N
ATOM      2  CA  PRO H  14      53.440 -73.630  34.533  1.00 20.01           C
ATOM      3  C   PRO H  14      54.482 -72.584  34.124  1.00 20.76           C
ATOM      4  O   PRO H  14      55.025 -72.627  33.021  1.00 16.34           O
ATOM      5  CB  PRO H  14      54.055 -74.895  35.134  1.00 22.06           C
ATOM      6  CG  PRO H  14      54.084 -75.862  33.972  1.00 25.16           C
ATOM      7  CD  PRO H  14      52.770 -75.608  33.294  1.00 17.36           C
ATOM      8  HD2 PRO H  14      52.801 -75.872  32.361  1.00 17.36           H
ATOM      9  HD1 PRO H  14      52.048 -76.072  33.746  1.00 17.36           H
ATOM     10  HG2 PRO H  14      54.830 -75.664  33.385  1.00 25.16           H
ATOM     11  HG1 PRO H  14      54.147 -76.775  34.292  1.00 25.16           H
ATOM     12  HA  PRO H  14      52.877 -73.212  35.203  1.00 20.01           H
ATOM     13  HB1 PRO H  14      54.949 -74.711  35.461  1.00 22.06           H
ATOM     14  HB2 PRO H  14      53.499 -75.228  35.856  1.00 22.06           H
ATOM     15  N   SER H  15      54.727 -71.646  35.038  1.00 21.70           N
ATOM     16  CA  SER H  15      55.670 -70.537  34.874  1.00 25.33           C
ATOM     17  C   SER H  15      55.049 -69.401  34.057  1.00 24.78           C
ATOM     18  O   SER H  15      55.581 -68.291  34.023  1.00 27.51           O
ATOM     19  CB  SER H  15      56.982 -71.005  34.219  1.00 25.20           C
ATOM     20  OG  SER H  15      56.914 -70.938  32.802  1.00 28.91           O
ATOM     21  H   SER H  15      54.335 -71.634  35.803  1.00 21.70           H
ATOM     22  HA  SER H  15      55.899 -70.163  35.739  1.00 25.33           H
ATOM     23  HB1 SER H  15      57.705 -70.434  34.524  1.00 25.20           H
ATOM     24  HG  SER H  15      56.769 -70.147  32.558  1.00 28.91           H
ATOM     25  HB2 SER H  15      57.151 -71.924  34.481  1.00 25.20           H
ATOM     26  N   GLN H  16      53.918 -69.678  33.412  1.00 24.55           N
ATOM     27  CA  GLN H  16      53.224 -68.673  32.611  1.00 29.39           C
ATOM     28  C   GLN H  16      52.340 -67.778  33.475  1.00 28.13           C
ATOM     29  O   GLN H  16      52.234 -67.987  34.681  1.00 26.35           O
ATOM     30  CB  GLN H  16      52.371 -69.346  31.533  1.00 31.67           C
ATOM     31  CG  GLN H  16      53.196 -70.112  30.524  1.00 44.80           C
ATOM     32  CD  GLN H  16      54.379 -69.303  30.030  1.00 48.55           C
ATOM     33  OE1 GLN H  16      54.213 -68.269  29.386  1.00 52.45           O
ATOM     34  NE2 GLN H  16      55.584 -69.766  30.342  1.00 55.07           N
ATOM     35  H   GLN H  16      53.530 -70.445  33.423  1.00 24.55           H
ATOM     36  HG2 GLN H  16      53.533 -70.922  30.937  1.00 44.80           H
ATOM     37  HG1 GLN H  16      52.641 -70.335  29.761  1.00 44.80           H
ATOM     38 HE22 GLN H  16      55.661 -70.489  30.801  1.00 55.07           H
ATOM     39 HE21 GLN H  16      56.287 -69.343  30.085  1.00 55.07           H
ATOM     40  HA  GLN H  16      53.888 -68.112  32.179  1.00 29.39           H
ATOM     41  HB1 GLN H  16      51.871 -68.665  31.056  1.00 31.67           H
ATOM     42  HB2 GLN H  16      51.761 -69.970  31.957  1.00 31.67           H
"""

pdb_str_2 = """
CRYST1   24.984   25.729   23.590  90.00  90.00  90.00 P 1
ATOM      1  N   PRO A 245      13.194  10.192  16.658  1.00 41.32           N
ANISOU    1  N   PRO A 245     5445   5107   5149   -761   -337   -188       N
ATOM      2  CA  PRO A 245      12.939  11.276  15.705  1.00 43.09           C
ANISOU    2  CA  PRO A 245     5616   5296   5462   -703   -345   -192       C
ATOM      3  C   PRO A 245      13.983  11.305  14.601  1.00 46.16           C
ANISOU    3  C   PRO A 245     6029   5612   5898   -683   -379   -133       C
ATOM      4  O   PRO A 245      15.086  10.768  14.728  1.00 44.69           O
ANISOU    4  O   PRO A 245     5890   5400   5691   -698   -398   -108       O
ATOM      5  CB  PRO A 245      13.007  12.541  16.569  1.00 42.50           C
ANISOU    5  CB  PRO A 245     5520   5200   5429   -665   -331   -270       C
ATOM      6  CG  PRO A 245      13.795  12.147  17.772  1.00 47.69           C
ANISOU    6  CG  PRO A 245     6219   5884   6018   -710   -338   -300       C
ATOM      7  CD  PRO A 245      13.504  10.698  18.006  1.00 45.37           C
ANISOU    7  CD  PRO A 245     5958   5649   5630   -763   -332   -248       C
ATOM      8  HD2 PRO A 245      14.279  10.246  18.375  1.00 45.37           H
ATOM      9  HD1 PRO A 245      12.744  10.590  18.598  1.00 45.37           H
ATOM     10  HG2 PRO A 245      14.740  12.283  17.601  1.00 47.69           H
ATOM     11  HG1 PRO A 245      13.515  12.679  18.533  1.00 47.69           H
ATOM     12  HA  PRO A 245      12.051  11.211  15.320  1.00 43.09           H
ATOM     13  HB1 PRO A 245      13.452  13.251  16.080  1.00 42.50           H
ATOM     14  HB2 PRO A 245      12.112  12.820  16.817  1.00 42.50           H
ATOM     15  N   LYS A 246      13.611  11.942  13.495  1.00 42.99           N
ANISOU   15  N   LYS A 246     5586   5194   5553   -642   -384   -103       N
ATOM     16  CA  LYS A 246      14.551  12.132  12.404  1.00 43.44           C
ANISOU   16  CA  LYS A 246     5657   5196   5651   -626   -410    -46       C
ATOM     17  C   LYS A 246      15.633  13.122  12.832  1.00 46.25           C
ANISOU   17  C   LYS A 246     6029   5476   6066   -612   -418    -67       C
ATOM     18  O   LYS A 246      15.332  14.110  13.510  1.00 45.93           O
ANISOU   18  O   LYS A 246     5978   5405   6070   -590   -399   -123       O
ATOM     19  CB  LYS A 246      13.837  12.652  11.156  1.00 49.81           C
ANISOU   19  CB  LYS A 246     6412   6022   6492   -584   -414      4       C
ATOM     20  CG  LYS A 246      12.652  11.809  10.713  1.00 54.70           C
ANISOU   20  CG  LYS A 246     6990   6749   7043   -615   -407      9       C
ATOM     21  CD  LYS A 246      13.071  10.649   9.829  1.00 62.40           C
ANISOU   21  CD  LYS A 246     8002   7745   7964   -674   -416     37       C
ATOM     22  CE  LYS A 246      11.928   9.661   9.640  1.00 71.25           C
ANISOU   22  CE  LYS A 246     9098   8967   9007   -746   -399     13       C
ATOM     23  NZ  LYS A 246      10.594  10.329   9.556  1.00 76.52           N
ANISOU   23  NZ  LYS A 246     9661   9743   9672   -714   -398     10       N
ATOM     24  HE1 LYS A 246      11.910   9.050  10.393  1.00 71.25           H
ATOM     25  HE2 LYS A 246      12.069   9.168   8.816  1.00 71.25           H
ATOM     26  H   LYS A 246      12.828  12.269  13.355  1.00 42.99           H
ATOM     27  HG2 LYS A 246      12.208  11.447  11.496  1.00 54.70           H
ATOM     28  HG1 LYS A 246      12.036  12.365  10.210  1.00 54.70           H
ATOM     29  HD1 LYS A 246      13.815  10.182  10.241  1.00 62.40           H
ATOM     30  HD2 LYS A 246      13.332  10.985   8.958  1.00 62.40           H
ATOM     31  HZ1 LYS A 246      10.608  11.094  10.010  1.00 76.52           H
ATOM     32  HZ3 LYS A 246       9.966   9.800   9.900  1.00 76.52           H
ATOM     33  HZ2 LYS A 246      10.393  10.501   8.706  1.00 76.52           H
ATOM     34  HA  LYS A 246      14.966  11.285  12.179  1.00 43.44           H
ATOM     35  HB1 LYS A 246      14.472  12.674  10.423  1.00 49.81           H
ATOM     36  HB2 LYS A 246      13.509  13.547  11.338  1.00 49.81           H
ATOM     37  N   PRO A 247      16.897  12.890  12.459  1.00 44.07           N
ANISOU   37  N   PRO A 247     5777   5176   5792   -629   -439    -35       N
ATOM     38  CA  PRO A 247      17.961  13.810  12.905  1.00 39.69           C
ANISOU   38  CA  PRO A 247     5226   4573   5283   -643   -446    -65       C
ATOM     39  C   PRO A 247      17.659  15.272  12.622  1.00 41.96           C
ANISOU   39  C   PRO A 247     5505   4774   5665   -619   -425    -77       C
ATOM     40  O   PRO A 247      17.848  16.127  13.497  1.00 43.51           O
ANISOU   40  O   PRO A 247     5712   4925   5896   -637   -407   -153       O
ATOM     41  CB  PRO A 247      19.188  13.316  12.126  1.00 43.94           C
ANISOU   41  CB  PRO A 247     5766   5120   5808   -656   -468     -8       C
ATOM     42  CG  PRO A 247      18.912  11.884  11.852  1.00 47.67           C
ANISOU   42  CG  PRO A 247     6260   5641   6212   -648   -469     24       C
ATOM     43  CD  PRO A 247      17.430  11.781  11.650  1.00 44.76           C
ANISOU   43  CD  PRO A 247     5884   5287   5837   -641   -451     19       C
ATOM     44  HD2 PRO A 247      17.201  11.896  10.714  1.00 44.76           H
ATOM     45  HD1 PRO A 247      17.097  10.929  11.971  1.00 44.76           H
ATOM     46  HG2 PRO A 247      19.193  11.346  12.609  1.00 47.67           H
ATOM     47  HG1 PRO A 247      19.387  11.607  11.053  1.00 47.67           H
ATOM     48  HA  PRO A 247      18.124  13.716  13.857  1.00 39.69           H
ATOM     49  HB1 PRO A 247      19.279  13.817  11.300  1.00 43.94           H
ATOM     50  HB2 PRO A 247      19.987  13.419  12.667  1.00 43.94           H
TER
HETATM   51  N   TAM H   2       9.323  12.496   7.335  1.00 20.00           N
HETATM   52  C   TAM H   2       8.060  12.492   8.002  1.00 20.00           C
HETATM   53  C1  TAM H   2       7.540  13.901   8.071  1.00 20.00           C
HETATM   54  C2  TAM H   2       8.386  11.881   9.335  1.00 20.00           C
HETATM   55  C3  TAM H   2       7.035  11.686   7.294  1.00 20.00           C
HETATM   56  C4  TAM H   2       7.128  14.539   6.744  1.00 20.00           C
HETATM   57  C5  TAM H   2       8.930  10.458   9.271  1.00 20.00           C
HETATM   58  C6  TAM H   2       5.660  11.992   7.821  1.00 20.00           C
HETATM   59  O4  TAM H   2       5.710  14.391   6.585  1.00 20.00           O
HETATM   60  O5  TAM H   2       7.872   9.487   9.299  1.00 20.00           O
HETATM   61  O6  TAM H   2       5.714  12.262   9.200  1.00 20.00           O
END
"""

pdb_str_3 = """
CRYST1   16.760   20.171   17.648  90.00  90.00  90.00 P 1
MODEL        1
ATOM      1  N   GLY A  -3      14.573   7.304   5.082  1.00 23.20           N
ATOM      2  CA  GLY A  -3      15.503   6.752   6.050  1.00 43.12           C
ATOM      3  C   GLY A  -3      16.822   7.516   6.092  1.00 10.33           C
ATOM      4  O   GLY A  -3      17.833   7.000   5.608  1.00 34.23           O
ATOM      6  HA2 GLY A  -3      15.692   5.828   5.822  1.00 43.12           H
ATOM      7  HA1 GLY A  -3      15.103   6.784   6.933  1.00 43.12           H
ATOM      8  N   PRO A  -2      16.855   8.759   6.667  1.00 43.42           N
ATOM      9  CA  PRO A  -2      18.084   9.573   6.756  1.00 72.12           C
ATOM     10  C   PRO A  -2      19.050   9.085   7.843  1.00 24.33           C
ATOM     11  O   PRO A  -2      20.269   9.138   7.662  1.00  1.42           O
ATOM     12  CB  PRO A  -2      17.569  10.986   7.098  1.00 65.32           C
ATOM     13  CG  PRO A  -2      16.078  10.915   7.005  1.00 23.11           C
ATOM     14  CD  PRO A  -2      15.713   9.483   7.257  1.00  3.14           C
ATOM     15  HD2 PRO A  -2      15.639   9.304   8.207  1.00  3.14           H
ATOM     16  HD1 PRO A  -2      14.884   9.250   6.810  1.00  3.14           H
ATOM     17  HG2 PRO A  -2      15.793  11.190   6.120  1.00 23.11           H
ATOM     18  HG1 PRO A  -2      15.682  11.493   7.676  1.00 23.11           H
ATOM     19  HA  PRO A  -2      18.527   9.578   5.893  1.00 72.12           H
ATOM     20  HB1 PRO A  -2      17.846  11.226   7.996  1.00 65.32           H
ATOM     21  HB2 PRO A  -2      17.923  11.625   6.460  1.00 65.32           H
ATOM     22  N   SER A  -1      18.485   8.603   8.974  1.00 54.30           N
ATOM     23  CA  SER A  -1      19.258   8.090  10.133  1.00 74.21           C
ATOM     24  C   SER A  -1      20.126   9.182  10.770  1.00 44.31           C
ATOM     25  O   SER A  -1      20.919   9.834  10.087  1.00 24.24           O
ATOM     26  CB  SER A  -1      20.129   6.881   9.741  1.00 35.31           C
ATOM     27  OG  SER A  -1      20.678   6.247  10.885  1.00 34.24           O
ATOM     28  H   SER A  -1      17.635   8.561   9.099  1.00 54.30           H
ATOM     29  HA  SER A  -1      18.619   7.793  10.799  1.00 74.21           H
ATOM     30  HB1 SER A  -1      20.854   7.187   9.174  1.00 35.31           H
ATOM     31  HG  SER A  -1      21.157   6.789  11.312  1.00 34.24           H
ATOM     32  HB2 SER A  -1      19.580   6.241   9.261  1.00 35.31           H
TER
ENDMDL
MODEL        2
ATOM   1753  N   GLY A  -3      15.598  12.155  12.730  1.00 23.20           N
ATOM   1754  CA  GLY A  -3      15.801  13.217  11.761  1.00 43.12           C
ATOM   1755  C   GLY A  -3      15.603  12.746  10.322  1.00 10.33           C
ATOM   1756  O   GLY A  -3      14.940  11.727  10.105  1.00 34.23           O
ATOM   1758  HA2 GLY A  -3      15.172  13.934  11.936  1.00 43.12           H
ATOM   1759  HA1 GLY A  -3      16.704  13.561  11.848  1.00 43.12           H
ATOM   1760  N   PRO A  -2      16.164  13.467   9.301  1.00 43.42           N
ATOM   1761  CA  PRO A  -2      16.028  13.090   7.880  1.00 72.12           C
ATOM   1762  C   PRO A  -2      16.904  11.891   7.491  1.00 24.33           C
ATOM   1763  O   PRO A  -2      16.479  11.039   6.705  1.00  1.42           O
ATOM   1764  CB  PRO A  -2      16.479  14.351   7.114  1.00 65.32           C
ATOM   1765  CG  PRO A  -2      16.651  15.418   8.147  1.00 23.11           C
ATOM   1766  CD  PRO A  -2      16.953  14.708   9.432  1.00  3.14           C
ATOM   1767  HD2 PRO A  -2      17.900  14.513   9.508  1.00  3.14           H
ATOM   1768  HD1 PRO A  -2      16.659  15.229  10.196  1.00  3.14           H
ATOM   1769  HG2 PRO A  -2      15.832  15.932   8.224  1.00 23.11           H
ATOM   1770  HG1 PRO A  -2      17.386  15.999   7.896  1.00 23.11           H
ATOM   1771  HA  PRO A  -2      15.094  12.906   7.692  1.00 72.12           H
ATOM   1772  HB1 PRO A  -2      17.317  14.174   6.659  1.00 65.32           H
ATOM   1773  HB2 PRO A  -2      15.799  14.602   6.470  1.00 65.32           H
ATOM   1774  N   SER A  -1      18.123  11.839   8.047  1.00 54.30           N
ATOM   1775  CA  SER A  -1      19.064  10.752   7.768  1.00 74.21           C
ATOM   1776  C   SER A  -1      19.650  10.188   9.066  1.00 44.31           C
ATOM   1777  O   SER A  -1      19.683   8.969   9.256  1.00 24.24           O
ATOM   1778  CB  SER A  -1      20.187  11.243   6.843  1.00 35.31           C
ATOM   1779  OG  SER A  -1      20.983  10.164   6.382  1.00 34.24           O
ATOM   1780  H   SER A  -1      18.429  12.428   8.594  1.00 54.30           H
ATOM   1781  HA  SER A  -1      18.592  10.034   7.318  1.00 74.21           H
ATOM   1782  HB1 SER A  -1      20.750  11.861   7.334  1.00 35.31           H
ATOM   1783  HG  SER A  -1      21.333   9.767   7.034  1.00 34.24           H
ATOM   1784  HB2 SER A  -1      19.791  11.690   6.079  1.00 35.31           H
TER
ENDMDL
"""

pdb_str_4 = """
CRYST1   17.826   22.060   19.146  90.00  90.00  90.00 P 1
ATOM      1  P     U A   2       7.236  16.525   9.726  1.00 37.21           P
ATOM      2  OP1   U A   2       6.663  17.060  10.993  1.00 38.75           O
ATOM      3  OP2   U A   2       8.650  16.805   9.385  1.00 34.84           O
ATOM      4  O5'   U A   2       7.029  14.947   9.685  1.00 34.31           O
ATOM      5  C5'   U A   2       5.756  14.354   9.974  1.00 37.02           C
ATOM      6  C4'   U A   2       5.821  12.860   9.763  1.00 36.81           C
ATOM      7  O4'   U A   2       5.957  12.552   8.350  1.00 36.96           O
ATOM      8  C3'   U A   2       7.025  12.178  10.388  1.00 36.55           C
ATOM      9  O3'   U A   2       6.846  11.969  11.775  1.00 36.22           O
ATOM     10  C2'   U A   2       7.106  10.884   9.592  1.00 36.94           C
ATOM     11  O2'   U A   2       6.138   9.930   9.980  1.00 38.55           O
ATOM     12  C1'   U A   2       6.755  11.383   8.191  1.00 36.22           C
ATOM     13  N1    U A   2       7.938  11.735   7.391  1.00 34.47           N
ATOM     14  C2    U A   2       8.652  10.705   6.795  1.00 33.67           C
ATOM     15  O2    U A   2       8.375   9.526   6.954  1.00 33.54           O
ATOM     16  N3    U A   2       9.706  11.110   6.014  1.00 33.13           N
ATOM     17  C4    U A   2      10.119  12.408   5.784  1.00 32.43           C
ATOM     18  O4    U A   2      11.043  12.620   5.000  1.00 31.05           O
ATOM     19  C5    U A   2       9.352  13.409   6.464  1.00 33.80           C
ATOM     20  C6    U A   2       8.316  13.048   7.223  1.00 33.46           C
ATOM     21  H4*   U A   2       5.000  12.459  10.088  1.00 36.81           H
ATOM     22  H3*   U A   2       7.826  12.702  10.232  1.00 36.55           H
ATOM     23  H2*   U A   2       7.997  10.505   9.648  1.00 36.94           H
ATOM     24 HO2*   U A   2       5.578   9.841   9.360  1.00 38.55           H
ATOM     25  H1*   U A   2       6.256  10.694   7.724  1.00 36.22           H
ATOM     26  H5    U A   2       9.576  14.307   6.377  1.00 33.80           H
ATOM     27 H5*1   U A   2       5.515  14.540  10.895  1.00 37.02           H
ATOM     28 H5*2   U A   2       5.082  14.734   9.388  1.00 37.02           H
ATOM     29  H3    U A   2      10.157  10.489   5.626  1.00 33.13           H
ATOM     30  H6    U A   2       7.829  13.711   7.657  1.00 33.46           H
HETATM   31  P   UMS A   3       8.115  12.049  12.757  1.00 35.65           P
HETATM   32  OP1 UMS A   3       7.608  12.006  14.146  1.00 37.56           O
HETATM   33  OP2 UMS A   3       8.986  13.173  12.329  1.00 35.79           O
HETATM   34  O5' UMS A   3       8.946  10.722  12.449  1.00 37.12           O
HETATM   35  C5' UMS A   3       8.323   9.447  12.591  1.00 36.88           C
HETATM   36  C4' UMS A   3       9.203   8.363  12.041  1.00 39.11           C
HETATM   37  O4' UMS A   3       9.187   8.277  10.585  1.00 38.36           O
HETATM   38  C3' UMS A   3      10.640   8.278  12.458  1.00 40.33           C
HETATM   39  O3' UMS A   3      10.895   8.001  13.828  1.00 40.80           O
HETATM   40  C2' UMS A   3      11.291   7.467  11.374  1.00 40.93           C
HETATM   41  C1' UMS A   3      10.496   7.904  10.133  1.00 38.75           C
HETATM   42  N1  UMS A   3      11.106   9.042   9.429  1.00 36.80           N
HETATM   43  C2  UMS A   3      12.013   8.736   8.436  1.00 35.25           C
HETATM   44  O2  UMS A   3      12.328   7.589   8.163  1.00 36.36           O
HETATM   45  N3  UMS A   3      12.557   9.822   7.786  1.00 33.98           N
HETATM   46  C4  UMS A   3      12.275  11.159   7.996  1.00 32.51           C
HETATM   47  O4  UMS A   3      12.826  12.001   7.302  1.00 33.01           O
HETATM   48  C5  UMS A   3      11.323  11.402   9.046  1.00 33.90           C
HETATM   49  C6  UMS A   3      10.817  10.354   9.743  1.00 34.62           C
HETATM   50  CA' UMS A   3      11.776   5.000  13.480  1.00 46.26           C
HETATM   51 SE2' UMS A   3      10.815   5.400  11.905  1.00 48.17          Se
"""

if (__name__ == "__main__"):
  t0 = time.time()
  run()
  print("OK. Time: %8.3f"%(time.time()-t0))
