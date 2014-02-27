from __future__ import division
from scitbx.array_family import flex
import math
from math import exp,pi,log,pow
import cPickle as pickle
import cStringIO as StringIO
from scitbx.lbfgs import run,termination_parameters,exception_handling_parameters,core_parameters


class minimizer:
  def __init__(self, d_i, psi_i, eta_rad, Deff):
    import sys
    self.safelog = -1. + math.log(sys.float_info.max)
    self.S = StringIO.StringIO()
    pickle.dump([d_i, psi_i, eta_rad, Deff],self.S,0)
    assert len(d_i) == len(psi_i)
    self.d_i = d_i
    self.psi_i = psi_i
    self.Nobs = len(d_i)
    self.escalate = 10. # 10 is a soft switch; 50-100 a hard switch
    self.x = flex.double([log(1./Deff), log(eta_rad)]) # parameters alpha, eta
    self.minimizer = run(
      target_evaluator=self,
      core_params=core_parameters(
        gtol=0.1
        # increasing the accuracy of the line search technique (default=0.9)
        # as suggested by source code.  Otherwise Deff is set unreasonably high
        # and the exponential blows up.
      ),
      termination_params = termination_parameters(
        traditional_convergence_test=False,
        drop_convergence_test_max_drop_eps=1.e-5,
        min_iterations=0,
        max_iterations = 100,
        max_calls=200),
      exception_handling_params=exception_handling_parameters(
         ignore_line_search_failed_rounding_errors=True,
         ignore_line_search_failed_step_at_lower_bound=True,#the only change from default
         ignore_line_search_failed_step_at_upper_bound=False,
         ignore_line_search_failed_maxfev=False,
         ignore_line_search_failed_xtol=False,
         ignore_search_direction_not_descent=False)
      )

    self.x=flex.exp(self.x)


  def functional_only(self,alpha,eta):

    print "Deff_ang",1./alpha,"FWmos_deg",eta*180./pi
    allobs = xrange(self.Nobs)
    f = 0.
    if False:
      from matplotlib import pyplot as plt
      psi_model = (self.d_i*alpha + eta)/2.
      plt.plot(1./self.d_i,self.psi_i,"r.")
      plt.plot(1./self.d_i,psi_model,"g.")
      plt.plot(1./self.d_i,-psi_model,"g.")
      plt.show()

    for i in allobs:
      psi_model = (self.d_i[i]*alpha + eta)/2.
      psi_i = self.psi_i[i]
      B = self.escalate / psi_model
      expBarg = B*(psi_i+psi_model)
      expBnegarg = -B*(psi_i-psi_model)

      if abs(expBarg) > self.safelog or abs(expBnegarg) > self.safelog:

        print "XXescalate",self.escalate
        print "XXpsi_model",psi_model
        print "XXexp",B,expBarg
        print "XXeta",eta
        print "XXDeff",1./alpha
        print self.S.getvalue()
        raise ValueError("max likelihood exp argument outside of math domain %f %f"%(expBarg,expBnegarg))

      fx = (0.5/psi_model)/(1+exp(expBarg ) ) * (1+exp(self.escalate))
      gx = 1./(1+exp(expBnegarg ) ) * (1+exp(self.escalate))
      prob = fx * gx
      f -= math.log(prob)
    return f


  def compute_functional_and_gradients(self):
    """The compute_functional_and_gradients() function

    @return Two-tuple of the value of the functional, and an
            <code>n</code>-long vector with the values of the
            gradients at the current position
    """

    alpha = exp(self.x[0])
    eta = exp(self.x[1])
    #print "alpha",alpha, "eta",eta
    allobs = xrange(self.Nobs)
    f = 0.
    partf_partP0 = 0.
    partf_partP1 = 0.

    f = self.functional_only(alpha,eta)

    for i in allobs:
      psi_model = (self.d_i[i]*alpha + eta)/2.
      part_psi_model_partP0 = 0.5 * self.d_i[i] * alpha
      part_psi_model_partP1 = 0.5 * eta

      psi_i = self.psi_i[i]
      B = self.escalate / psi_model

      partB_partP0 = (-self.escalate/(psi_model*psi_model))*part_psi_model_partP0
      partB_partP1 = (-self.escalate/(psi_model*psi_model))*part_psi_model_partP1
      expB = exp( B * (psi_i + psi_model) )
      expBneg = exp( -B * (psi_i - psi_model) )
      partSpos_partP0 = expB * ((psi_i+psi_model)*partB_partP0 + B*part_psi_model_partP0)
      partSpos_partP1 = expB * ((psi_i+psi_model)*partB_partP1 + B*part_psi_model_partP1)

      partSneg_partP0 = expBneg * ((-psi_i+psi_model)*partB_partP0 + B*part_psi_model_partP0)
      partSneg_partP1 = expBneg * ((-psi_i+psi_model)*partB_partP1 + B*part_psi_model_partP1)

      Spos = 1. + expB
      Sneg = 1. + expBneg

      expnu = 1. + exp(self.escalate)
      partG_partP0 = -expnu*pow(Sneg,-2)*partSneg_partP0
      partG_partP1 = -expnu*pow(Sneg,-2)*partSneg_partP1

      Sfac = 2.*psi_model*Spos
      partF_partP0 = -expnu*pow(Sfac,-2)*2*(psi_model*partSpos_partP0 + Spos*part_psi_model_partP0)
      partF_partP1 = -expnu*pow(Sfac,-2)*2*(psi_model*partSpos_partP1 + Spos*part_psi_model_partP1)

      fx = (0.5/psi_model)/(Spos) * expnu
      gx = (1./Sneg) * expnu
      prob = fx * gx
      part_prob_partP0 = fx*partG_partP0 + gx*partF_partP0
      part_prob_partP1 = fx*partG_partP1 + gx*partF_partP1


      partf_partP0 -= (1./prob) * part_prob_partP0
      partf_partP1 -= (1./prob) * part_prob_partP1


    print f, [partf_partP0,partf_partP1],"analytical"
    #self.fd_compute_functional_and_gradients()


    return (f, flex.double([partf_partP0,partf_partP1]))


  def fd_compute_functional_and_gradients(self):
    """The compute_functional_and_gradients() function

    @return Two-tuple of the value of the functional, and an
            <code>n</code>-long vector with the values of the
            gradients at the current position
    """
    EPSILON = 0.000001

    alpha = exp(self.x[0])
    eta = exp(self.x[1])
    aplus = exp(self.x[0]+EPSILON)
    aminu = exp(self.x[0]-EPSILON)
    eplus = exp(self.x[1]+EPSILON)
    eminu = exp(self.x[1]-EPSILON)

    allobs = xrange(self.Nobs)
    f = 0.
    partf_partalpha = 0.
    partf_parteta = 0.
    partf_partnu = 0.

    f = self.functional_only(alpha,eta)

    fd_partf_partalpha = (self.functional_only(aplus,eta) -
                          self.functional_only(aminu,eta)) / (2.*EPSILON)

    fd_partf_parteta = (self.functional_only(alpha,eplus) -
                          self.functional_only(alpha,eminu)) / (2.*EPSILON)

    print f, [fd_partf_partalpha,fd_partf_parteta],"finite diff"
    print


    return (f, flex.double([fd_partf_partalpha,fd_partf_parteta]))
if __name__=="__main__":
  Deff=3031.86582722
  eta_rad = 0.000466410948822
  psi_i = flex.double([0.0006334354051280837, -0.0002374482102549014, -0.0002904909028471741, 0.0011826729893182895, 0.000410928438641641, -0.00124596265535444, -0.00021073006263523284, 2.093758396869777e-05, 0.00013926185459742, 4.1804791078049327e-07, 0.0005488235136727886, -9.193766688284655e-05, 8.44164318416186e-05, 0.00017546468776326354, 8.556690954803574e-05, -0.0003036138955810559, -0.000641357099097601, -0.0002244689650400115, 0.0024344760117975877, 0.00014360518608511725, 0.0004629662852427153, 0.0010858564953247383, -0.0001894719504276195, -0.0004220364347353991, -0.00016480563546219582, -7.844441933222163e-05, 0.0003252131531280895, -0.0005136803614743484, 4.5978946903056804e-05, 0.0010255392857963421, 0.0006644982357545689, -0.0007174042461201835, 0.0009742587761427171, 0.0024434586226267443, 0.00045561395760178476, 8.915319478679247e-05, 0.0005236885101564813, 0.0002856271291591659, -0.0026734526609776222, 0.00033306436288244306, -0.00022754281024372315, 0.00023817253689034415, -0.0002520749898691968, -0.0020537511660755365, 0.00020729453680532877, -2.354914713029257e-05, 0.0002876895854414163, 0.001716027465036208, 0.00030875292516916055, 0.00028734095022527615, 0.000690293382372606, 9.792237509768104e-05, 0.0007307128060078471, 0.00019444481369464814, 0.0005980270995420993, 0.0009460483933354358, 0.0005870499944482794, -0.00011039230639688934, -0.0004808531781895475, 0.0018870161528584625, -0.0003639091021999277, 0.0005519908037482245, 0.0004329619246624209, -0.00015085445344515053, 0.0006282538001626667, -0.0007732943616816869, -0.00032749371035270856, 0.000654930282155595, -0.00023549605807420977, -0.0005891241811741804, -0.001015592507240478, 9.246491356739758e-05, -0.0003231223275328174, 0.0004315647971386343, 0.0006499518590635939, 0.000400054650432406, -0.0004822487654504704, 0.00027532639996442285, -0.000978602851334643, -0.0006213760059380183, 0.0003760896353606164, 0.0005196509460713409, 0.00046415390276214013, -0.00015462263783441285, 0.00027762919906122496, 0.0018081142933046867, 0.00037768318649323456, -0.00024789833570362747, 0.00023662192723274434, 0.00016966215728721011, -0.00033361760550367045, 0.0019367119474373712, 0.0005384334393999256, 0.0007318635462986153, 0.00017086715430940608, 7.859867939243422e-05, -0.00020751446869054133, 4.994364572469607e-05, -0.0003824554400449278, -0.00026521631430174915, 0.00014213714869980813, 0.00032378952104965194, 0.00043881016031337784, -5.463509415655856e-05, -6.045567179850129e-05, 0.00016833309698749229, -0.0009034322958119932, 0.0003272749274387823, 0.0001278213552360918, 6.918587207431909e-05, -0.00018906814027630796, 0.0005493447463055587, -0.0003473573489120576, -0.0005756446264375274, -0.0005810317073863452, 0.00016823626895044565, -0.0007121302419254515, -0.0006446641830389517, 0.00021457706495682201, -0.001412815997421152, 0.0008049965900551816, 0.0006739688433907676, -0.000678084916577125, 0.0030964461975499288, 0.0004752110867421634, -0.0016101620722278956, 0.00021391028011932275, 0.0002860580859305863, 0.0006361019143261609, -0.00018401253708537975, -5.504805202934844e-06, -0.0003182879168637159, 0.000346408756262901, -0.00017056597173038918, -0.00044799476065611975, -0.0028675925127297436, -0.0006978869592003578, 4.2832889980511555e-05, 0.00089016728168247, 0.0003420927123675246, -0.0003982221462937286, 0.00044318297487696727, -0.0005969711504537665, 0.0009111071547058384, -0.0002038300440046238, 0.00011222789250645929, 0.0004948503818038209, 0.000573759835322318, 0.001717392937439531, -0.002467551854588084, 0.0005062520631107385, 5.553236213844266e-05, 0.00022044850244526192, -0.0018649150377643446, 3.936315541818528e-05, 0.0014308829990956617, -0.0011578832483421064, -0.0016054935013721523, -0.0008640481845045424, -8.971217742970833e-06, -0.0004958325004491824, 0.00011426889745855636, 0.000292717376135336, 0.001017079613404912, -0.00012882548748991722, 0.0005809114055173677, -0.0001951028012238056, -0.0027759773250265914, -3.0209564912715713e-06, 0.00154305151450003, 0.00018446039254867836, -3.925711690358909e-05, -0.0004924523623733561, 0.0005333718539225543, -0.00025765087226601, -0.00014519511157405664, 0.00024576785641819003, 0.001987392470563443, -0.0015908076085160842, -0.0007568934908868987, 8.855355118073257e-05, -0.0019037301453423694, -0.0021770063469934817, 7.461655325738224e-05, 0.000462175497743351, 0.0005210146349210425, 0.0003568038603044771, 0.0004241373873707148, -8.741021895009534e-05, 0.000772174239832898, 0.00017911252172103442, -0.000829847159513602, 0.0004203673237735533, 0.0003133743498532781, 0.000593575431918884, 0.0003135947687543809, -0.0003645869544373544, 0.0006683068563840346, -0.00020235259595415136, 0.001349220965705753, -0.0020340670591110946, -0.00041769434735829526, -0.0004981501214739162, 0.0006561989502845671, 0.000669760559782651, 0.0003326533779073069, -0.00010200669939649307, -3.2386995946181664e-05, 0.0003588285620225712, -0.0011167815661772362, -0.00011310316823843577, -0.0005182390526102326, 0.0003693433943514537, 0.002024436428121275, 6.0997105182865915e-06, -0.0007129132283254319, 0.0001501522318223662, 7.891047353648714e-05, -0.0004697314657214998, -0.000254897406114653, -0.0011103794670150483, 0.0005577120453981939, 0.00018114685966135773, 0.0005649927159838467, 0.00010925773866533162, 0.0013098308064900127, 0.00023154969051534776, -0.0004285451549980843, -0.0019214804443266583, 0.00010493961393166586, 0.0005837263906034756, 1.6543113254048606e-05, 0.0007172526298240186, -0.0005886852065927795, -0.00041255570143160653, -1.9459509347031384e-05, 0.000291402983547018, 0.0023631139065301253, -0.0003622504630621428, 0.0005492262697211277, 0.0003626606834520612, -0.00011725487830694665, 0.0006326408323113677, -0.0004532188740792162, -4.913443894179339e-05, -0.0008856524048359493, 0.00039130561315146005, -0.0010554441938547467, 0.0015911591768067678, 0.000296077168203888, 0.0008531550437984701, -0.0012470707492369434, -0.000368735092190866, -0.00048243265489017283, -0.00023880076540505645, -0.00016790348150706597, -0.00043873361796145714, -0.0002913480105513663, -0.0014296564172633214, 0.0007144624338873749, 0.0008088391432223697, -0.0011814675472588269, 0.0005638966756702765, -0.0002339603888997489, -0.0003776586914134988, -0.00037553793891285383, 0.0003748364378593961, 0.00023082270999786524, -1.3543625332733382e-05, 0.000566545676492891, -0.0009057346890978281, -0.00017866687749221904, -0.001526913004987003, -0.0006720993529390468, 0.0002823459570464341, -0.0004450740135123615, 0.00047640791508281007, -0.0005958240895908187, -0.00017715665612174923, -0.00010080123864633324, 0.0004917574222360578, 0.0001138285229133618, 0.002465914169858405, 0.0005670600537261423, 0.00045625687103809787, -0.0007840586889616584, 0.00046319556626305263, -0.0010976838525113457, 0.0010725441033398978, -0.0016254531068346048, 0.0004917971699042798, 0.00013902751830996868, -0.00043005402852254687, -0.0011106718487453404, 0.00029494742812678375, 0.0009486028938960881, 0.0001670867459708942, -8.840799842513007e-05, 0.0006746453911334185, -0.00017727808190206177, 0.00010086513848317247, 0.00046922516881331053, 0.0004774571484740222, -1.0290901111203135e-05, 9.520162344092303e-05, 0.0003648541536849967, 0.00033538690108845924, -0.000960327363637412, 0.00013873546600079437, -0.0010232619266481232, -0.0020280638581877384, 0.0001567455390613696, 0.0014669352199031922, 6.782005972102013e-05, 0.0002352303451780971, -0.001821343288153858, -0.0001712081861449313, 0.00031081395506616337, 0.0009544698011518178, 0.0005112243747540542, 0.0002887346396428908, 0.00043685134241168444, 0.00042168939876234974, -0.0005880744341518443, 0.0003798195971433711, -0.0007184547018713771, 0.0003951313087168337, 9.562387290242932e-05, 0.0004981695413882228, -0.0005385273212058099, 0.000296764200450422, 0.00018748698401748, 0.00041741041859787474, 0.0008462363197504522, 0.0008791662395954949, 0.00019411531039167294, 0.0003920548724702504, -9.015497541533188e-05, 0.0004629664422454387, -0.0002590798902835395, 0.000619215728770989, -0.0006211483528622371, -8.748231255274872e-05, 0.0006053661413481926, 4.5199125752450315e-05, -0.00023116139793226005, -0.0013307036436834081, -0.0005217065577529301, 0.00020006978081617486, -0.0001372390219034168, 0.00018060544092251136, 0.0005113312361672036, 0.0002546040087449535, -0.0010117507630612913, 0.0002952656134773918, 3.685950063999722e-05, -0.002747881898223466, 4.469499790684989e-05, -8.64748135254941e-05, 0.0005410004348519962, 0.0002314964958088268, 0.0006949176380301295, 0.000481122335409309, -2.122607107855415e-06, 0.00033344339389782934, -0.00024176241352626937, 0.0003918579268656973, 0.0002879429302788722, 0.0002304104299996654, -0.0002932895815460491, 0.000270787659132965, -0.00022084427101548627, 0.0006743541201956554, -0.0007728670561707907, 0.00030135299603558974, -0.0006349737943818644, 0.0014365359029781866, -0.00046582802376684716, 1.5076197293738287e-05, 0.0003060496436397627, -0.00041029524968308923, -0.00015788139131724642, -0.0006897275444536018, 0.0004277381531197532, 0.00018702754553908004, 8.135788411259676e-05, -6.500751918266024e-06, -2.6289169547485133e-05, -0.0003809997311837905, 0.0008348293597586775, 0.0016111498319801166, -0.00035119055433390195, -0.001966510648060297, -0.001854197411075898, 9.623351486095679e-05, -0.0008975372710879016, 0.0002706853163176684, 0.00036832523220991164, 0.00027188591827131633, 0.0006172510979453672, 0.0010293698245156036, 0.0009252472588028924, -0.0002246569735282741, -0.000748439743863933, -0.00012681198711444338, -0.00024567151469336875, 0.000656837442748095, -0.0005604178701421391, 0.0007551552199390202, -0.0003587364527235524, -0.0003827050223400733, 0.00044335143140818774, 0.000845681099730772, -0.0004030859844640091, -0.0003294503463532275, 8.43833530135475e-06, 7.077903698494563e-05, 0.0015367722976354224, 0.0007166888660092409, 0.00031153766141145807, -0.000740150523125915, -0.0004208589331863031, 0.0010652399740192213, -0.0023318701940420986, 0.0011310873173778011, -0.0006987673480852243, 0.00028439181687007163, 0.00017189112510128236, 0.00012854852934878624, -0.0006356655893574796, -0.00017936708576597155, -5.1008730145817176e-05, -0.0006359047693557081, -0.00022095414634034296, 0.00043389480769891615, -0.00019156693945777045, -0.002034224252790802, 0.0005512118898921187, -0.00024372352518081702, 0.000500004620145614, 0.00046175745498500706, -0.0007875543712366582, 0.00011863247056773087, 0.00021952671299415615, 0.0026756915014432016, 0.002441093552811954, 0.00022963195358635362, -0.0009702125771836496, 8.240836326731117e-05, 0.0008214496531351811, 0.0003961329180581964, -0.0005430279556713573, 0.0004192266490019224, -0.0005862721448841857, 0.00020754331836952812, -0.000995228733370721, -0.0018821621462388287, 0.0030356300703595364, 0.0009888778436200859, 0.00026823687672701405, 0.0017078286119160963, -0.0006692785161963609, 0.0013962584972315815, 0.0010006047458768325, 0.00133878266456956, 0.00018680364364215193, -0.003126239803787991, 0.0008611476990846082, 0.0018530185046467208, -0.00038825335064714833, -0.0031494901010388422])
  d_i = flex.double([12.496125481007214, 5.37052061631852, 6.372901019116141, 12.254605390492443, 3.910692511204004, 15.364205358835587, 3.533629764565976, 5.304086248169242, 4.295690946012782, 4.810330279569616, 5.942651381509386, 6.732743795247132, 5.380219179235266, 5.176393854534195, 5.811451588887256, 9.86073770314327, 11.267954583147361, 8.051455824084014, 13.489749140504834, 4.262394408511081, 3.818664410371657, 9.146082465149595, 8.242144162922713, 6.998491803231956, 4.894566521635404, 10.538589954935542, 6.382100027448593, 6.739630640642708, 5.5720909369083795, 15.054184635104907, 5.602889558297534, 13.730239811504623, 8.834441325322528, 9.492459547512885, 4.4983049201266, 3.9472171964825526, 3.328081815517008, 6.102028074353887, 16.407749108432828, 7.4156834217017344, 12.33350632786428, 6.03929885968487, 10.112507267237426, 14.650970980703876, 4.354227890485642, 4.695835417519907, 5.308106305362877, 8.453074986016325, 4.610608490414736, 4.722677452030006, 4.522801150866567, 3.82988191020755, 17.303874026661116, 4.03098593858027, 6.645656252928453, 8.056889155395, 4.321350649642642, 4.470668902320949, 14.343022592219818, 11.634007634359032, 4.890912761964096, 7.745481157022565, 5.839804656396404, 3.81075724021023, 4.47599713621185, 8.88761560270757, 11.685191865651504, 4.99961976234618, 10.699399034308513, 5.789359755492081, 13.863427026668797, 8.957101840984425, 4.6411803580998985, 6.899566496421001, 8.568480519904112, 6.094202875387393, 10.26981985311339, 5.419346749424954, 12.131292783154962, 6.99657332957382, 2.928495136106975, 4.181326552706507, 4.328388215172019, 60.82350852196105, 3.7435046369156937, 8.214856764357352, 3.663624280559579, 5.15606066981975, 4.022474727761948, 3.460724085695112, 11.631629286533432, 9.485493288700827, 5.77452327854987, 6.067476499231714, 6.0541293208259095, 4.071762384305521, 6.812339742428627, 7.522097048418081, 16.179850215756723, 7.276357407186171, 5.304236279678581, 5.385333251169153, 4.720812443721588, 4.56105729909986, 13.093266557650766, 3.775383246849266, 7.820027063004571, 3.5168797740851456, 4.194967692763481, 25.204969624981516, 4.313206024194667, 7.574946313210257, 4.349272617183872, 15.24300821066979, 7.471511020269636, 5.90314382112432, 9.292926744985913, 14.219976039433982, 3.765569124064841, 9.62393299818646, 6.285899198025237, 5.089897013758276, 5.2501393830119865, 10.148226023325186, 5.034012631526682, 17.123810028063566, 3.839074892262106, 4.244233433501858, 4.57307566332094, 4.441108740950086, 5.644192425382879, 8.60282145831157, 5.060826474178333, 4.2739585775683935, 5.651692721633443, 48.65880681756884, 6.012416513212133, 21.21395651030999, 7.450329833462853, 4.417173963910764, 14.003924960571423, 4.564377591020246, 11.552659629181875, 7.492673234859181, 8.916318001238407, 4.612941352080246, 5.4872279141852225, 5.164663993158436, 19.920912918974874, 13.982863812203536, 7.597573158666213, 4.195756645048118, 6.204916116630871, 11.325085069834348, 3.712961032648373, 11.892005739297405, 10.51076480540115, 16.9565805497686, 15.142523290046086, 5.367351351195613, 4.2955657222016805, 5.03260891119849, 3.303967314482843, 7.841211790446599, 6.207961728665808, 7.492695529508777, 5.213933005710513, 15.1559302852355, 4.48129831940034, 13.070222041640184, 6.823222818766578, 4.106187481834676, 8.9441638850514, 3.871495075440654, 5.57343676231097, 4.094305666316854, 4.781151892971771, 13.489359644149292, 8.084700528360443, 9.050703383562649, 4.951089307222705, 14.418462557615156, 8.719472459583852, 6.392619555642581, 3.815692392843197, 42.24456424522369, 4.014854115378061, 3.1634932005038094, 5.732006234347408, 19.498633707649024, 3.6416727204379358, 9.5995718586154, 4.01408849076983, 4.122409679813531, 7.233480195110401, 5.139197297633144, 4.259370913647693, 3.9617898922070265, 7.196191950919739, 23.667578941975965, 9.249512180234662, 10.105711440619709, 7.16380030366351, 8.004553767574249, 7.027696766568184, 3.8779607714021993, 5.635875360232505, 11.510964885873696, 4.583928064240949, 14.052921618937866, 11.05100183058865, 6.12845593198528, 4.389050372448064, 11.01396313119337, 5.472063684012923, 13.818586876714331, 3.6729155613357247, 4.362528418640924, 4.906130925602242, 19.109307885207294, 14.443823945219787, 4.199486023147086, 4.012415775813075, 4.103568073708873, 9.419368652051263, 5.816915703079742, 5.680206147132252, 6.438077455875232, 13.693940569847175, 4.16937689551419, 4.933177894685913, 4.202502749203123, 4.205417716885984, 10.126403214726263, 7.473309968863036, 4.41112528911597, 8.121906312155456, 16.84742672297724, 4.912004822233266, 7.422518170511507, 29.607749061198362, 8.49851077266509, 6.700728072829796, 4.844292208906807, 4.762622701277455, 6.88968915462277, 5.904376987583908, 13.105330027735533, 9.802149798776435, 4.346689095666191, 5.211576597375097, 14.896116135402433, 5.238860650917186, 9.214013514566533, 5.315942359494999, 4.948910899444225, 9.050477090354756, 4.7714573134350795, 7.049819056592982, 5.125504244246154, 4.569039536035176, 9.123189618130095, 4.720570837577256, 4.659282741214248, 4.9115987368151055, 4.138631188117357, 4.09008938951596, 16.06930651273918, 5.070524208800141, 4.955528855250392, 8.636520586444291, 4.0236231198615755, 8.319115913550725, 7.637760226263567, 3.752374640232403, 5.8891498037736, 4.586144634471143, 5.407991465753737, 6.5447043084982885, 4.810548959988931, 4.226637781218769, 5.514553740920427, 8.721537473813992, 6.089475955698423, 4.0498662455841075, 8.469248378460339, 6.493004212326931, 11.71228607093485, 7.485554733525809, 13.863471534357938, 4.149813946121394, 7.76369241569881, 7.829665530857823, 11.449833160270478, 3.461150815247223, 5.586519230216418, 3.912160675664224, 5.4130519143910485, 7.309340988429196, 6.39772855344777, 7.196352963841612, 4.321892379055801, 4.180002755791975, 9.79925845308538, 4.437595161067206, 4.077163490716227, 3.518824922481227, 8.243859021989627, 4.293829981070743, 13.600860937908754, 15.818869148716827, 8.038342769166135, 27.9676802031808, 3.7954597635657636, 3.7681576916794, 11.21841997593632, 4.50519185363571, 4.248583197565239, 5.441423873628011, 6.582236136875411, 4.269009859165721, 4.006609217094649, 3.4499824689304246, 10.152538170367176, 4.853563986741619, 8.757816910560292, 4.685099084301029, 5.182771502238263, 6.175011439990506, 4.813893046318137, 5.245315060313983, 4.687759629878175, 4.027458256210232, 8.299170224121836, 7.258302751624717, 5.726666001978309, 3.5387581154953653, 3.732783931626053, 11.785021499785902, 4.260359845754977, 7.920285943017924, 9.921151247826097, 4.895282408700041, 6.3809201856609095, 7.388193009298489, 4.998942479288759, 7.864085768997293, 12.385608096963919, 4.340213295084278, 7.13225437905609, 6.870945078665965, 3.917568785581144, 4.007201686146074, 8.289551628970083, 10.678050225656552, 7.692900331546507, 17.209386824187273, 5.617022330577095, 5.096631830883907, 5.755584905102438, 5.815557660784512, 5.545857004980865, 6.363880567661076, 4.787428496579198, 3.817998379533764, 4.265808507121314, 6.694116933427199, 3.603656593455515, 6.399892861988105, 5.010452461299101, 3.167737577353923, 6.2733786513655305, 4.218896251710065, 7.560516452704808, 6.218962837118315, 14.418411789191287, 8.541553111988163, 6.348210353381056, 4.582088955770606, 4.7048798816712845, 8.979717270590134, 5.3840194549175875, 6.971525003589123, 3.8518734917684405, 4.519782744719283, 11.534278859319143, 4.886627903066536, 6.614765070369275, 5.550772592782202, 4.588578037352825, 10.055803374100478, 5.80703853874472, 16.71470174654123, 12.999475697363897, 4.172609416700113, 7.035850618852968, 6.313718680533122, 5.883730067159367, 3.9383882241309722, 4.152771317888124, 7.153086494495075, 6.108742919516945, 5.857862683330688, 15.09554146963721, 4.413477865264932, 4.833890795031411, 6.0365419977395005, 6.505972426698061, 4.465033292442182, 7.118929701084873, 6.739195966546418, 4.828646422818781, 6.449496429887082, 17.151082456014, 4.534905663341792, 3.8980523879878612, 4.2493847050360465, 8.569680382520453, 5.155830635721968, 5.1890171932141245, 15.333610147764423, 5.1504739777243715, 7.4714004918334815, 20.82257529950839, 7.870922932054178, 7.985936256728403, 3.636833419154957, 4.036675709894154, 10.047967668433717, 6.097540748846113, 4.614977881717082, 3.372262012615576, 8.11522512148733, 3.574993651140074, 8.04455663085853, 4.220409035691168, 9.63952269295869, 4.487317468055194, 5.382934232506098, 4.424911477840285, 4.332049432938316, 8.834308455656553, 5.838738943774013, 3.633765397287114, 18.787047900267638, 16.905764556687412, 3.467193680800522, 8.040273269281153, 3.6415070338608033, 7.046866166525815, 3.7988391750080437, 10.563461621911275, 6.917636324477366, 10.248950369608416, 5.016357547529524, 9.707940282836985, 13.846550734260434, 19.79263595985994, 7.525693533823855, 3.909750772351232, 14.695435562625814, 7.826561485909148, 9.46004259845192, 6.877868747512286, 12.434327938231078, 3.087677172795908, 11.57943133769928, 4.304608777648071, 14.758942891036405, 4.595167128766594, 9.767325535313098])
  minimizer(d_i, psi_i, eta_rad, Deff)
