
from pyomo.environ import *
from pyomo.core import Objective, Var, Constraint
from pyomo.opt import SolverFactory
import sys, os
from matplotlib import pyplot as plt
import numpy as np
from IPython import embed as IP
from temoa_model import temoa_create_model
from temoa_initialize import DemandConstraintErrorCheck
from temoa_rules import PeriodCost_rule

from IPython import embed as IP

def pf_result(dat,dat1):
    M = temoa_create_model()

    def Capacity_Constraint ( M, p, s, d, t, v, scenario):

    if t in M.tech_hourlystorage:
        return Constraint.Skip
        
    produceable = (
      (   value( M.CapacityFactorTech[s, d, t, v, scenario] )
        * value( M.CapacityToActivity[ t ] )
        * value( M.SegFrac[s, d]) )
        * value( M.ProcessLifeFrac[p, t, v] )
      * M.V_Capacity[t, v]
    )

    expr = (produceable >= M.V_Activity[p, s, d, t, v])
    return expr        


    M.del_component('CapacityFactorTech')
    M.del_component('Capacity_Constraint')
    M.num_scenarios                = Param()
    M.scenario                     = Set(ordered=True, rule=lambda M: range(1, value(M.num_scenarios) + 1))
    M.CapacityFactorTech           = Param(M.time_season, M.time_of_day, M.tech_all, M.scenario)
    M.CapacityConstraint           = Constraint( M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario, rule=Capacity_Constraint )


    data1 = DataPortal(model = M)
    data1.load(filename=dat)
    data1.load(filename=dat1)
    instance = M.create_instance(data1)

def temoa_robust(dat, dat2):
    M = temoa_create_model()
    def Robust_rule ( M ):
        regret = sum(M.regret[scenario] for scenario in M.scenario)
        risk = value(M.phi) * sum(M.z[p,s,d,c,dem,scenario] for p,s,d,c,dem,scenario in M.DemandConstraint)
        cost = sum( PeriodCost_rule(M, p) for p in M.time_optimize )
        
        return (cost + regret + risk)

    def Demand_Constraint ( M, p, s, d, dem, scenario ):
        supply = sum(
          M.V_FlowOut[p, s, d, S_i, S_t, S_v, dem]
    
          for S_t, S_v in M.helper_commodityUStreamProcess[ p, dem ]
          for S_i in M.helper_ProcessInputsByOutput[ p, S_t, S_v, dem ]
        ) 
    
        DemandConstraintErrorCheck( supply, p, s, d, dem )
    
        expr = (supply + M.z[p, s, d, dem, scenario] == M.elecDemand[p, s, d, dem])
    
        return expr

    def Capacity_Constraint ( M, p, s, d, t, v):

    if t in M.tech_hourlystorage:
        return Constraint.Skip
        
    produceable = (
      (   value( M.CapacityFactorTech[s, d, t, v, scenario] )
        * value( M.CapacityToActivity[ t ] )
        * value( M.SegFrac[s, d]) )
        * value( M.ProcessLifeFrac[p, t, v] )
      * M.V_Capacity[t, v]
    )

    expr = (produceable >= M.V_Activity[p, s, d, t, v])
    return expr

    def regret_Constraint(M, scenario):
        expr = (M.regret = sum( PeriodCost_rule(M, p) for p in M.time_optimize ) - value(M.scenarioCost[scenario]))
        return expr

    def real_obj(M): #STOCH ELASTIC
        a = sum( PeriodCost_rule(M, p) for p in M.time_optimize )
        expr = (a >= 0)
        return expr
        
    M.del_component('TotalCost')
    M.del_component('DemandConstraint')
    M.del_component('M.DemandActivityConstraint_psdtv_dem_s0d0')
    M.del_component('DemandActivityConstraint')
    M.del_component('CapacityFactorTech')
    M.del_component('Capacity_Constraint')
    # Efficiency: all the parameters
    M.num_scenarios                = Param()
    M.scenario                     = Set(ordered=True, rule=lambda M: range(1, value(M.num_scenarios) + 1))
    M.CapacityFactorTech           = Param(M.time_season, M.time_of_day, M.tech_all, M.scenario)
    M.z                            = Var(M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario, domain=Reals)
    M.regret                       = Var(M.scenario, domain = Reals)
    M.phi                          = Param()
    M.scenarioCost                 = Param(M.scenario)
    
    M.TotalCost                    = Constraint(rule=real_obj)
    M.DemandConstraint             = Constraint( M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario, rule=Demand_Constraint )
    M.CapacityConstraint           = Constraint( M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario, rule=Capacity_Constraint )
    M.regret_Constraint            = Constraint(M.scenario, rule=M.regret_Constraint)

    M.Robust = Objective(rule=Robust_rule, sense=minimize)

    data1 = DataPortal(model = M)
    data1.load(filename=dat)
    data1.load(filename=dat1)
    instance = M.create_instance(data1)

    optimizer = SolverFactory('cplex')
    results = optimizer.solve(instance)
    instance.solutions.load_from(results)




Robust_run():
    model = temoa_create_model()
    #dat = '/mnt/disk2/nspatank/Efficiency_nonlinear/data_files/US_National_ELC.dat'
    dat = '/D/temoa/for_git/temoa/data_files/test_Simple.dat'
    dat1 = '/D/temoa/for_git/temoa/data_files/scenarios.dat'
    scenario_cost = solve_dm(model, dat)

    instance = temoa_robust(dat, dat2)
    optimizer = SolverFactory('ipopt')

    optimizer.options['max_iter'] = 10000
    results = optimizer.solve(instance, keepfiles=True, tee=True)

    instance.solutions.load_from(results)
    fp = open('results.csv', 'w')
    dm = open('demand.csv', 'w')
    print >>fp, '\"', instance.name, '\"'
    print >>fp, '\"Model Documentation: ', instance.doc, '\"'
    print >>fp, '\"Solver Summary\"'
    print >>fp, '\"', results['Solver'][0], '\"'
    # Objective
    print >>fp, '\"Objective function is:', value(instance.Robust), '\"'
    print >>fp, '\"Total Cost is:', value(instance.TotalCost.body), '\"'
    print >>fp, '\"Consumer Cost is:', value(instance.consumer_cost.body), '\"'
    for v in instance.component_objects(Var, active=True):
        varobject = getattr(instance, str(v))
        #IP()
        print >> fp, ""
        print >> fp, "\"Variable: %s\", \"Notes: %s\"" % (v, varobject.doc)
        print ("fixing"+str(v))
        for index in varobject:
            varobject[index].fixed = True
            print>>fp, "\"" + str(index) + "\"", varobject[index].value


if __name__ == "__main__":
    Robust_run()
    sys.stdout.write('\a\a')
    sys.stdout.flush()