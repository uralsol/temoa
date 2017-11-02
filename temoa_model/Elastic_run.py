from pyomo.environ import *
from pyomo.core import Objective, Var, Constraint
from pyomo.opt import SolverFactory
import sys
from matplotlib import pyplot as plt
import numpy as np
from IPython import embed as IP

from temoa_elastic_model import *
model = temoa_create_elastic_model()

model.dual  = Suffix(direction=Suffix.IMPORT)
model.rc    = Suffix(direction=Suffix.IMPORT)
model.slack = Suffix(direction=Suffix.IMPORT)
model.lrc   = Suffix(direction=Suffix.IMPORT)
model.urc   = Suffix(direction=Suffix.IMPORT)

fp = open('results.csv', 'w')
def sensitivity():
    dat = '/mnt/disk2/nspatank/sudan_elastic/data_files/S_Sudan_delay.dat'
    dat1 = '/mnt/disk2/nspatank/sudan_elastic/temoa_model/price.dat'
    data = DataPortal(model = model)
    data.load(filename=dat)
    data.load(filename=dat1)
    instance = model.create_instance(data)
    optimizer = SolverFactory('cplex')
    results = optimizer.solve(instance, suffixes=['dual', 'rc', 'slack', 'lrc'])
    instance.solutions.load_from(results)
    print >>fp, '\"', instance.name, '\"'
    print >>fp, '\"Model Documentation: ', instance.doc, '\"'
    print >>fp, '\"Solver Summary\"'
    print >>fp, '\"', results['Solver'][0], '\"'
    # Objective

    obj = list(instance.component_data_objects( Objective ))
    if len( obj ) > 1:
        msg = '\nWarning: More than one objective.  Using first objective.\n'
        SE.write( msg )

    # This is a generic workaround.  Not sure how else to automatically discover the objective name
    obj_name, obj_value = obj[0].cname(True), value( obj[0] )
    IP()
    for v in sorted(instance.component_objects(Var, active=True)):
        if str(v) != 'V_DemandSegment':
            varobject = getattr(instance, str(v))
            #IP()
            print >> fp, ""
            print >> fp, "\"Variable: %s\", \"Notes: %s\"" % (v, varobject.doc)
            #IP()
            print >> fp, "\"" + str(v) + "\"", 'LOWER', 'VALUE', 'UPPER', 'REDUCED-COST'
            #IP()
            print ("fixing"+str(v))
            for index in varobject:
                varobject[index].fixed = True
                #IP()
                print>>fp, "\"" + str(index) + "\"", varobject[index].lb is None and '-INF' or varobject[index].lb, \
                varobject[index].value, varobject[index].ub is None and '+INF' or varobject[index].ub

    print "           Key                      elast       lb       Dem*DSD    V_Demand      ub          ref_Price         dual_of_dem     dual_of_elast_dem"
    i=0
    for p, s, d, dem  in sorted(instance.V_Demand.keys()):
        key = p, s, d, dem
        #IP()
        print "%35s  %2g    %10g    %8g  %10g   %8g  %15g   %19g    %19g" %\
                (key, value(instance.Elast[key]), instance.V_Demand[key].lb,
                value(instance.Demand[p, dem]) * value(instance.DemandSpecificDistribution[s, d, dem]),
                value(instance.V_Demand[key]), instance.V_Demand[key].ub,
                value(instance.Price[key]), instance.dual[instance.DemandConstraint.items()[i][1]],
                instance.dual[instance.DemandElasticityConstraint.items()[i][1]])
        if i < len(instance.DemandConstraint.items())-1:
            i += 1
        else:
            sys.exit(1)

if __name__ == "__main__":
    sensitivity()
    # do_LCcalculate()
    # plot_LCOE()
