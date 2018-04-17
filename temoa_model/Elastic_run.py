from pyomo.environ import *
import sys
from pyomo.core import Objective, Var, Constraint
from pyomo.opt import SolverFactory
import numpy as np

from temoa_model import temoa_create_model   
import temoa_run

from IPython import embed as IP

model = temoa_create_model()
model.dual  = Suffix(direction=Suffix.IMPORT)
dat = '/D/temoa/for_git/temoa/data_files/utopia-15.dat'
data = DataPortal(model = model)
data.load(filename=dat)
model.del_component('M.DemandActivityConstraint_psdtv_dem_s0d0')
model.del_component('DemandActivityConstraint')

instance = model.create_instance(data)
optimizer = SolverFactory('glpk')
results = optimizer.solve(instance, suffixes=['dual'])
instance.solutions.load_from(results)

price_data = open("price.dat", "w") #create a new file

ConstantDemandConstraint = instance.DemandConstraint
Demand = instance.Demand
DEMAND_RANGE = 0.95 # Max/MinDemand = (1 +/- DEMAND_RANGE)* Demand
DEMAND_SEGMENTS = 71 # number of steps

print >> price_data, """\
data;

param: MinDemand    MaxDemand  :=
    # year      # min    # max
"""
for key in sorted(Demand.sparse_keys()):
    if DEMAND_RANGE < 1.0:
        for l in key:
            print >> price_data, "%10s" % l,
        print >> price_data, "    %10g    %10g    " % ((1 - DEMAND_RANGE) * Demand[key], (1 + DEMAND_RANGE) * Demand[key])
    else:
        for l in key:
            print >> price_data, "%10s" % l,
        print >> price_data, "    %10g    %10g    " % (0.01, (1 + DEMAND_RANGE) * Demand[key])

print >> price_data, "    ;\n"
print >> price_data, """\
param: Price    Elast:=
    # year   # season   # time_of_day   # demand    # price    # elasticity
"""
for item in sorted(ConstantDemandConstraint.items()):
    price = instance.dual[item[1]]
    print >> price_data, "%10s    %10s    %10s    %10s    %10g    %10g    " % \
    (item[0][0], item[0][1], item[0][2], item[0][3], instance.dual[item[1]],0.34)

print >> price_data, "    ;\n"
print >> price_data, "param num_demand_segments := %d ;\
    # number of segments in the demand range" % DEMAND_SEGMENTS

price_data.close()


#from temoa_elastic_model import *
M = temoa_create_model()
#from temoa_elastic import *
M.dual  = Suffix(direction=Suffix.IMPORT)
M.lrc   = Suffix(direction=Suffix.IMPORT)
M.urc   = Suffix(direction=Suffix.IMPORT)

from temoa_initialize import DemandConstraintErrorCheck
from temoa_rules import PeriodCost_rule
def TotalWelfare_rule ( M ):

    consumer_costs = sum(( value(M.DemandSegment_bound_value[p, s, d, dem]) - M.V_DemandSegment[p, s, d, dem, z])
       * value(M.PriceSegment[p, s, d, dem, z])
       for (p, s, d, dem, z) in M.DemandConstraint_psdcz)
    
    producer_costs = sum( PeriodCost_rule(M, p) for p in M.time_optimize )
    return (producer_costs - consumer_costs)

# ELASTIC: Note that the Demand constraint sets the variable V_Demand to be equal to supply.
def Demand_Constraint ( M, p, s, d, dem ):

    supply = sum(
      M.V_FlowOut[p, s, d, S_i, S_t, S_v, dem]

      for S_t, S_v in M.helper_commodityUStreamProcess[ p, dem ]
      for S_i in M.helper_ProcessInputsByOutput[ p, S_t, S_v, dem ]
    )

    DemandConstraintErrorCheck( supply, p, s, d, dem )

    expr = (supply == M.V_Demand[p, s, d, dem])

    return expr

#ELASTIC: Definition of V_Demand in terms of MinDemand and non-zero V_DemandSegment
def DemandElasticity_Constraint(M, p, s, d, dem):
    r"""\
Defines the variable V_Demand as the sum of the MinDemand and non-zero V_DemandSegment
variables.
"""

    expr = (M.V_Demand[p, s, d, dem] == M.MaxDemand[p, dem] * M.DemandSpecificDistribution[s, d, dem] -
            sum([M.V_DemandSegment[p, s, d, dem, z]
            for z in M.demand_segment]))
    return expr



# ELASTIC: Bounds (size) of each V_DemandSegment variable
def DemandSegment_bound(M, p, s, d, dem):
    r"""\
    Defines the (0.0, upper bound) of each V_DemandSegment variable.
    """
    diff = ((value(M.MaxDemand[p, dem]) - value(M.MinDemand[p, dem])) * value(M.DemandSpecificDistribution[s, d, dem])
            / value(M.num_demand_segments))

    return diff

#Elastic
def DemandSegment_bound_rule(M, p, s, d, dem, z):
    r"""\
    Defines the (0.0, upper bound) of each V_DemandSegment variable.
    """
    diff = ((value(M.MaxDemand[p, dem]) - value(M.MinDemand[p, dem])) * value(M.DemandSpecificDistribution[s, d, dem])
            / value(M.num_demand_segments))

    return (0.0, diff)

# ELASTIC: Definition of Price from the price-demand elasticity curve.
#Here price is independent of the demand variable which  makes me suspicios - Neha
def PriceSegment_rule(M, p, s, d, dem, z):
    r"""\
    Defines the price at each V_DemandSegment using the price-demand elasticity curve.
    """
    P0 = value(M.Price[p, s, d, dem])
    D0 = value(M.Demand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem])
    minb = value(M.MinDemand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem])
    diff = (value(M.MaxDemand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem]) - minb) / value(M.num_demand_segments)
    D = minb + (z-0.5) * diff
    e = 1.0 / value(M.Elast[p, s, d, dem])

    P = (P0 * (D / D0) ** -e)#/(1 - e))
    return P

# ELASTIC: Utility function that calculates the midpoint of each demand segment.
# Note: this is only used in reporting and is not part of the model.
def DemandSegment_midpoint_rule(M, p, s, d, dem, z):

    minb = value(M.MinDemand[p, dem]) * M.DemandSpecificDistribution[s, d, dem]
    diff = (value(M.MaxDemand[p, dem]) * M.DemandSpecificDistribution[s, d, dem] - minb) / value(M.num_demand_segments)
    D = minb + (z - 0.5) * diff
    return D


def Demand_rule(M, p, s, d, dem):
    return value(M.Demand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem])

def Demand_bounds(M, p, s, d, dem):
    return (value(M.MinDemand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem]),
            value(M.MaxDemand[p, dem]) * value(M.DemandSpecificDistribution[s, d, dem]))

fp = open('results.csv', 'w')

def Elastic_run():
    M.del_component('TotalCost')
    M.del_component('DemandConstraint')
    M.del_component('M.DemandActivityConstraint_psdtv_dem_s0d0')
    M.del_component('DemandActivityConstraint')

    M.num_demand_segments      = Param()
    M.demand_segment           = Set(ordered=True, rule=lambda M: range(1, value(M.num_demand_segments) + 1))
    M.Elast                    = Param(M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand)
    M.Price                    = Param(M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand)
    M.MinDemand                = Param(M.time_optimize, M.commodity_demand)
    M.MaxDemand                = Param(M.time_optimize, M.commodity_demand)
    M.V_Demand                 = Var(M.DemandConstraint_psdc, initialize=Demand_rule,bounds=Demand_bounds)
    M.DemandConstraint_psdcz   = M.DemandConstraint_psdc * M.demand_segment
    M.DemandSegment_bound_value = Param(M.DemandConstraint_psdc, initialize=DemandSegment_bound)
    M.V_DemandSegment          = Var(M.DemandConstraint_psdcz,bounds=DemandSegment_bound_rule, initialize=0.0)
    M.PriceSegment             = Param(M.DemandConstraint_psdcz, initialize=PriceSegment_rule)
    M.DemandSegment_midpoint   = Param(M.DemandConstraint_psdcz, initialize=DemandSegment_midpoint_rule)
    M.DemandElasticityConstraint = Constraint(M.DemandConstraint_psdc, rule=DemandElasticity_Constraint)
    M.DemandConstraint         = Constraint( M.DemandConstraint_psdc, rule=Demand_Constraint )

    M.TotalWelfare             = Objective(rule=TotalWelfare_rule, sense=minimize)

    dat = '/D/temoa/for_git/temoa/data_files/utopia-15.dat'
    dat1 = '/D/temoa/for_git/temoa/temoa_model/price.dat'
    data = DataPortal(model = M)
    data.load(filename=dat)
    data.load(filename=dat1)
    instance = M.create_instance(data)
    optimizer = SolverFactory('glpk')
    results = optimizer.solve(instance, suffixes=['dual','lrc'])
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
    for v in sorted(instance.component_objects(Var, active=True)):
        if str(v) != 'V_DemandSegment':
            varobject = getattr(instance, str(v))
            print >> fp, ""
            print >> fp, "\"Variable: %s\", \"Notes: %s\"" % (v, varobject.doc)
            print >> fp, "\"" + str(v) + "\"", 'LOWER', 'VALUE', 'UPPER'
            print ("fixing"+str(v))
            for index in varobject:
                varobject[index].fixed = True
                print>>fp, "\"" + str(index) + "\"", varobject[index].lb is None and '-INF' or varobject[index].lb, \
                varobject[index].value, varobject[index].ub is None and '+INF' or varobject[index].ub

    print "           Key                      elast       lb       Dem*DSD    V_Demand      ub          ref_Price         dual_of_dem     dual_of_elast_dem"
    i=0
    for p, s, d, dem  in sorted(instance.V_Demand.keys()):
        key = p, s, d, dem
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
    Elastic_run()

