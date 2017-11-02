DEMAND_RANGE = 0.25 # Max/MinDemand = (1 +/- DEMAND_RANGE)* Demand
DEMAND_SEGMENTS = 717 # number of steps
from pyomo.environ import *
from temoa_model import temoa_create_model   
import temoa_run
import sys
from IPython import embed as IP
from pyomo.core import Objective, Var, Constraint
from pyomo.opt import SolverFactory

model = temoa_create_model()
model.dual  = Suffix(direction=Suffix.IMPORT)
dat = '/mnt/disk2/nspatank/sudan_elastic/data_files/S_Sudan_delay.dat'
data = DataPortal(model = model)
data.load(filename=dat)

instance = model.create_instance(data)
optimizer = SolverFactory('cplex')
results = optimizer.solve(instance, suffixes=['dual'])
instance.solutions.load_from(results)

price_data = open("price.dat", "w") #create a new file

ConstantDemandConstraint = instance.DemandConstraint
Demand = instance.Demand

print >> price_data, """\
data;

param: MinDemand    MaxDemand  :=
    # year      # min    # max
"""
for key in sorted(Demand.sparse_keys()):
    if DEMAND_RANGE < 1.0:
        for l in key:
            print >> price_data, "%10s" % l,
        print >> price_data, "    %10g    %10g    " % \
            ((1 - DEMAND_RANGE) * Demand[key],
             (1 + DEMAND_RANGE) * Demand[key])
    else:
        for l in key:
            print >> price_data, "%10s" % l,
        print >> price_data, "    %10g    %10g    " % \
            (0.01,
             (1 + DEMAND_RANGE) * Demand[key])

print >> price_data, "    ;\n"
print >> price_data, """\
param: Price    Elast:=
    # year   # season   # time_of_day   # demand    # price    # elasticity
"""
for item in sorted(ConstantDemandConstraint.items()):
    price = instance.dual[item[1]]
    print >> price_data, "%10s    %10s    %10s    %10s    %10g    %10g    " % \
    (item[0][0], item[0][1], item[0][2], item[0][3], instance.dual[item[1]],1.4)

print >> price_data, "    ;\n"
print >> price_data, "param num_demand_segments := %d ;\
    # number of segments in the demand range" % DEMAND_SEGMENTS
