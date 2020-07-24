##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
This package provides the necessary constraints for solid phase properties of
an iron-based oxygen carrier
Components - Fe2O3, Fe3O4, Al2O3

Equations written in this model were primarily derived from:
National Institute of Standards and Technology, NIST Chemistry WebBook,
https://webbook.nist.gov/chemistry/ (accessed March 10, 2018).

"""

# Import Pyomo libraries
from pyomo.environ import (Constraint,
                           Param,
                           Reals,
                           value,
                           Var)
from pyomo.util.calc_var_value import calculate_variable_from_constraint
from pyomo.opt import SolverFactory

# Import IDAES cores
from idaes.core import (declare_process_block_class,
                        MaterialFlowBasis,
                        PhysicalParameterBlock,
                        StateBlockData,
                        StateBlock,
                        Component,
                        SolidPhase)
from idaes.core.util.initialization import (fix_state_vars,
                                            revert_state_vars,
                                            solve_indexed_blocks)
from idaes.core.util.misc import add_object_reference
from idaes.core.util.model_statistics import (
    degrees_of_freedom,
    number_unfixed_variables_in_activated_equalities)
import idaes.logger as idaeslog

# Some more information about this module
__author__ = "Chinedu Okoli"


# Set up logger
_log = idaeslog.getLogger(__name__)


@declare_process_block_class("SolidPhaseThermoParameterBlock")
class PhysicalParameterData(PhysicalParameterBlock):
    """
    Property Parameter Block Class

    Contains parameters and indexing sets associated with properties for
    methane CLC.
    """

    def build(self):
        '''
        Callable method for Block construction.
        '''
        super(PhysicalParameterData, self).build()

        self._state_block_class = SolidPhaseThermoStateBlock

        # Create Phase object
        self.Sol = SolidPhase()

        # Create Component objects
        self.Fe2O3 = Component()
        self.Fe3O4 = Component()
        self.Al2O3 = Component()

    # -------------------------------------------------------------------------
        """ Pure solid component properties"""

        # Mol. weights of solid components - units = kg/mol. ref: NIST webbook
        mw_comp_dict = {'Fe2O3': 0.15969, 'Fe3O4': 0.231533, 'Al2O3': 0.10196}
        self.mw_comp = Param(
                    self.component_list,
                    mutable=False,
                    initialize=mw_comp_dict,
                    doc="Molecular weights of solid components [kg/mol]")

        # Skeletal density of solid components - units = kg/m3. ref: NIST
        dens_mass_comp_sol_dict = {'Fe2O3': 5250, 'Fe3O4': 5000, 'Al2O3': 3987}
        self.dens_mass_comp_sol = Param(
                                    self.component_list,
                                    mutable=False,
                                    initialize=dens_mass_comp_sol_dict,
                                    doc='Particle density of solid components'
                                        '[kg/m3]')

        # Ideal gas spec. heat capacity parameters(Shomate) of
        # components - ref: NIST webbook. Shomate equations from NIST.
        # Parameters A-E are used for cp calcs while A-H are used for enthalpy
        # calc.
        # 1e3*cp_comp = A + B*T + C*T^2 + D*T^3 + E/(T^2)
        # where T = Temperature (K)/1000, and cp_comp = (kJ/mol.K)
        # H_comp = H - H(298.15) = A*T + B*T^2/2 + C*T^3/3 +
        # D*T^4/4 - E/T + F - H where T = Temp (K)/1000 and H_comp = (kJ/mol)
        cp_param_dict = {
                        ('Al2O3', 1): 102.4290,
                        ('Al2O3', 2): 38.74980,
                        ('Al2O3', 3): -15.91090,
                        ('Al2O3', 4): 2.628181,
                        ('Al2O3', 5): -3.007551,
                        ('Al2O3', 6): -1717.930,
                        ('Al2O3', 7): 146.9970,
                        ('Al2O3', 8): -1675.690,
                        ('Fe3O4', 1): 200.8320000,
                        ('Fe3O4', 2): 1.586435e-7,
                        ('Fe3O4', 3): -6.661682e-8,
                        ('Fe3O4', 4): 9.452452e-9,
                        ('Fe3O4', 5): 3.18602e-8,
                        ('Fe3O4', 6): -1174.1350000,
                        ('Fe3O4', 7): 388.0790000,
                        ('Fe3O4', 8): -1120.8940000,
                        ('Fe2O3', 1): 110.9362000,
                        ('Fe2O3', 2): 32.0471400,
                        ('Fe2O3', 3): -9.1923330,
                        ('Fe2O3', 4): 0.9015060,
                        ('Fe2O3', 5): 5.4336770,
                        ('Fe2O3', 6): -843.1471000,
                        ('Fe2O3', 7): 228.3548000,
                        ('Fe2O3', 8): -825.5032000}
        self.cp_param = Param(self.component_list,
                              range(1, 10),
                              mutable=False,
                              initialize=cp_param_dict,
                              doc="Shomate equation heat capacity parameters")

        # Std. heat of formation of comp. - units = kJ/(mol comp) - ref: NIST
        enth_mol_form_comp_dict = {'Fe2O3': -825.5032, 'Fe3O4': -1120.894,
                                   'Al2O3': -1675.690}
        self.enth_mol_form_comp = Param(
                self.component_list,
                mutable=False,
                initialize=enth_mol_form_comp_dict,
                doc="Component molar heats of formation [kJ/mol]")

    # -------------------------------------------------------------------------
        """ Mixed solid properties"""
        # These are setup as fixed vars to allow for parameter estimation

        # Particle size
        self.particle_dia = Var(domain=Reals,
                                initialize=1.5e-3,
                                doc='Diameter of solid particles [m]')
        self.particle_dia.fix()

        # Particle porosity:
        # The porosity of the OC particle is assumed to be a known parameter,
        # and it is calculated from the known bulk density of the fresh OC
        # particle (3251.75 kg/m3), and the known skeletal density of the
        # fresh OC particle (calculated from the known composition of the
        # fresh particle, and the skeletal density of its components)
        self.particle_porosity = Var(domain=Reals,
                                     initialize=1.5e-3,
                                     doc='Porosity of oxygen carrier [-]')
        self.particle_porosity.fix()

        # TODO -provide reference
        # Minimum fluidization velocity - EPAT value used for Davidson model
        self.velocity_mf = Var(domain=Reals,
                               initialize=0.039624,
                               doc='Velocity at minimum fluidization [m/s]')
        self.velocity_mf.fix()

        # Minimum fluidization voidage - educated guess as rough
        # estimate from ergun equation results (0.4) are suspicious
        self.voidage_mf = Var(domain=Reals,
                              initialize=0.45,
                              doc='Voidage at minimum fluidization [-]')
        self.voidage_mf.fix()

        # Particle thermal conductivity
        self.therm_cond_sol = Var(domain=Reals,
                                  initialize=12.3e-3,
                                  doc='Thermal conductivity of solid'
                                  'particles [kJ/m.K.s]')
        self.therm_cond_sol.fix()

    @classmethod
    def define_metadata(cls, obj):
        obj.add_properties({
                'flow_mass': {'method': None, 'units': 'kg/s'},
                'temperature': {'method': None, 'units': 'K'},
                'mass_frac_comp': {'method': None, 'units': None},
                'dens_mass_sol': {'method': '_dens_mass_sol',
                                  'units': 'kg/m3'},
                'cp_mol_comp': {'method': '_cp_mol_comp',
                                'units': 'kJ/mol.K'},
                'cp_mass': {'method': '_cp_mass', 'units': 'kJ/kg.K'},
                'enth_mass': {'method': '_enth_mass', 'units': 'kJ/kg'},
                'enth_mol_comp': {'method': '_enth_mol_comp',
                                  'units': 'kJ/mol'}})

        obj.add_default_units({'time': 's',
                               'length': 'm',
                               'mass': 'kg',
                               'amount': 'mol',
                               'temperature': 'K',
                               'energy': 'kJ',
                               'holdup': 'kg'})


class _SolidPhaseThermoStateBlock(StateBlock):
    """
    This Class contains methods which should be applied to Property Blocks as a
    whole, rather than individual elements of indexed Property Blocks.
    """
    def initialize(blk, state_args=None, hold_state=False,
                   state_vars_fixed=False, outlvl=idaeslog.NOTSET,
                   solver="ipopt", optarg={"tol": 1e-8}):
        """
        Initialization routine for property package.
        Keyword Arguments:
            state_args : Dictionary with initial guesses for the state vars
                         chosen. Note that if this method is triggered
                         through the control volume, and if initial guesses
                         were not provided at the unit model level, the
                         control volume passes the inlet values as initial
                         guess.
                         Keys for the state_args dictionary are:
                         flow_mass, temperature, and mass_frac_comp
            outlvl : sets output level of initialization routine
            optarg : solver options dictionary object (default=None)
            solver : str indicating whcih solver to use during
                     initialization (default = "ipopt")
            hold_state : flag indicating whether the initialization routine
                         should unfix any state variables fixed during
                         initialization (default=False).
                         - True - states varaibles are not unfixed, and
                                 a dict of returned containing flags for
                                 which states were fixed during
                                 initialization.
                        - False - state variables are unfixed after
                                 initialization by calling the
                                 relase_state method
        Returns:
            If hold_states is True, returns a dict containing flags for
            which states were fixed during initialization.
        """
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="properties")
        solve_log = idaeslog.getSolveLogger(blk.name, outlvl, tag="properties")

        init_log.info_high('Starting initialization')

        # Deactivate the constraints specific for outlet block i.e.
        # when defined state is False
        for k in blk.keys():
            if blk[k].config.defined_state is False:
                blk[k].sum_component_eqn.deactivate()

        # Fix state variables if not already fixed
        if state_vars_fixed is False:
            flags = fix_state_vars(blk, state_args)
        else:
            # Check when the state vars are fixed already result in dof 0
            for k in blk.keys():
                if degrees_of_freedom(blk[k]) != 0:
                    raise Exception("State vars fixed but degrees of freedom "
                                    "for state block is not zero during "
                                    "initialization.")

        # Set solver options
        opt = SolverFactory(solver)
        opt.options = optarg

        # ---------------------------------------------------------------------
        # Initialise values
        for k in blk.keys():
            if hasattr(blk[k], "density_constraint"):
                calculate_variable_from_constraint(
                            blk[k].dens_mass_sol,
                            blk[k].density_constraint)

            if hasattr(blk[k], "mixture_heat_capacity_eqn"):
                calculate_variable_from_constraint(
                            blk[k].cp_mass,
                            blk[k].mixture_heat_capacity_eqn)

            if hasattr(blk[k], "mixture_enthalpy_eqn"):
                calculate_variable_from_constraint(
                            blk[k].enth_mass,
                            blk[k].mixture_enthalpy_eqn)

            for j in blk[k]._params.component_list:

                if hasattr(blk[k], "cp_shomate_eqn"):
                    calculate_variable_from_constraint(blk[k].cp_mol_comp[j],
                                                       blk[k].cp_shomate_eqn[j]
                                                       )

                if hasattr(blk[k], "enthalpy_shomate_eqn"):
                    calculate_variable_from_constraint(
                            blk[k].enth_mol_comp[j],
                            blk[k].enthalpy_shomate_eqn[j])

        # Solve property block if non-empty
        free_vars = 0
        for k in blk.keys():
            free_vars += number_unfixed_variables_in_activated_equalities(
                blk[k])

        if free_vars > 0:
            with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
                res = solve_indexed_blocks(opt, [blk], tee=slc.tee)
        else:
            res = ""
        init_log.info_high("Initialization complete {}.".format(
                            idaeslog.condition(res))
                           )

        # ---------------------------------------------------------------------
        if state_vars_fixed is False:
            if hold_state is True:
                return flags
            else:
                blk.release_state(flags)

    def release_state(blk, flags, outlvl=0):
        """
        Method to relase state variables fixed during initialization.
        Keyword Arguments:
            flags : dict containing information of which state variables
                    were fixed during initialization, and should now be
                    unfixed. This dict is returned by initialize if
                    hold_state=True.
            outlvl : sets output level of of logging
        """
        if flags is None:
            return

        # Unfix state variables
        revert_state_vars(blk, flags)

        # Activate state variable related constraints
        for k in blk.keys():
            if blk[k].config.defined_state is False:
                blk[k].sum_component_eqn.activate()

        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="properties")
        init_log.info_high('States released.')

@declare_process_block_class("SolidPhaseThermoStateBlock",
                             block_class=_SolidPhaseThermoStateBlock)
class SolidPhaseThermoStateBlockData(StateBlockData):
    """
    Property package for gas phase properties of methane combustion in CLC FR
    """

    def build(self):
        """
        Callable method for Block construction
        """
        super(SolidPhaseThermoStateBlockData, self).build()

        # Object reference for molecular weight if needed by CV1D
        # Molecular weights
        add_object_reference(self, "mw",
                             self.config.parameters.mw_comp)

        self._make_state_vars()

    def _make_state_vars(self):
        """List the necessary state variable objects."""
        self.flow_mass = Var(initialize=1.0,
                             domain=Reals,
                             doc='Component mass flowrate [kg/s]')
        self.mass_frac_comp = Var(
            self._params.component_list,
            initialize=1 / len(self._params.component_list),
            doc='State component mass fractions [-]')
        self.temperature = Var(initialize=298.15,
                               domain=Reals,
                               doc='State temperature [K]')

        # Create standard constraints
        # Sum mass fractions if not inlet block
        if self.config.defined_state is False:
            def sum_component_eqn(b):
                return 1e2 == 1e2 * sum(b.mass_frac_comp[j]
                                        for j in b._params.component_list)
            self.sum_component_eqn = Constraint(rule=sum_component_eqn)

    def _dens_mass_sol(self):
        # Skeletal density of OC solid particles
        self.dens_mass_sol = Var(domain=Reals,
                                 initialize=3251.75,
                                 doc='Skeletal density of OC solid particles'
                                 '[kg/m3]')

        def density_constraint(b):
            return (b.dens_mass_sol * sum(b.mass_frac_comp[j] /
                                          b._params.dens_mass_comp_sol[j]
                                          for j in b._params.component_list) ==
                    1)
        try:
            # Try to build constraint
            self.density_constraint = Constraint(
                                            rule=density_constraint)
        except AttributeError:
            # If constraint fails, clean up so that DAE can try again later
            self.del_component(self.dens_mass_sol)
            self.del_component(self.density_constraint)
            raise

    def _cp_mol_comp(self):
        # Pure component solid heat capacities
        self.cp_mol_comp = Var(self._params.component_list,
                               domain=Reals,
                               initialize=1.0,
                               doc="Pure component solid heat capacities "
                               "[kJ/mol.K]")

        def pure_component_cp_mol(b, j):
            return b.cp_mol_comp[j] == 1e-3*(
                        b._params.cp_param[j, 1] +
                        b._params.cp_param[j, 2]*(b.temperature*1e-3) +
                        b._params.cp_param[j, 3]*(b.temperature*1e-3)**2 +
                        b._params.cp_param[j, 4]*(b.temperature*1e-3)**3 +
                        b._params.cp_param[j, 5]/((b.temperature*1e-3)**2))
        try:
            # Try to build constraint
            self.cp_shomate_eqn = Constraint(self._params.component_list,
                                             rule=pure_component_cp_mol)
        except AttributeError:
            # If constraint fails, clean up so that DAE can try again later
            self.del_component(self.cp_mol_comp)
            self.del_component(self.cp_shomate_eqn)
            raise

    def _cp_mass(self):
        # Mixture heat capacities
        self.cp_mass = Var(domain=Reals,
                           initialize=1.0,
                           doc="Mixture heat capacity, mass-basis [kJ/kg.K]")

        def cp_mass(b):
            return b.cp_mass == sum(b.cp_mol_comp[j]*b.mass_frac_comp[j]
                                    * (1/b._params.mw_comp[j])
                                    for j in b._params.component_list)
        try:
            # Try to build constraint
            self.mixture_heat_capacity_eqn = Constraint(rule=cp_mass)
        except AttributeError:
            # If constraint fails, clean up so that DAE can try again later
            self.del_component(self.cp_mass)
            self.del_component(self.mixture_heat_capacity_eqn)
            raise

    def _enth_mol_comp(self):
        # Pure component vapour enthalpies
        self.enth_mol_comp = Var(
                self._params.component_list,
                domain=Reals,
                initialize=1.0,
                doc="Pure component enthalpies [kJ/mol]")

        def pure_comp_enthalpy(b, j):
            return b.enth_mol_comp[j] == (
                    b._params.cp_param[j, 1]*(b.temperature*1e-3) +
                    b._params.cp_param[j, 2]*((b.temperature*1e-3)**2)/2 +
                    b._params.cp_param[j, 3]*((b.temperature*1e-3)**3)/3 +
                    b._params.cp_param[j, 4]*((b.temperature*1e-3)**4)/4 -
                    b._params.cp_param[j, 5]/(b.temperature*1e-3) +
                    b._params.cp_param[j, 6] -
                    b._params.cp_param[j, 8])
        try:
            # Try to build constraint
            self.enthalpy_shomate_eqn = Constraint(self._params.component_list,
                                                   rule=pure_comp_enthalpy)
        except AttributeError:
            # If constraint fails, clean up so that DAE can try again later
            self.del_component(self.enth_mol_comp)
            self.del_component(self.enthalpy_shomate_eqn)
            raise

    def _enth_mass(self):
        # Mixture mass enthalpy
        self.enth_mass = Var(domain=Reals,
                             initialize=0.0,
                             doc='Mixture specific enthalpy [kJ/kg]')
        try:
            # Try to build constraint
            self.mixture_enthalpy_eqn = Constraint(expr=(
                        self.enth_mass == sum(
                                self.mass_frac_comp[j] *
                                self.enth_mol_comp[j]
                                * (1/self._params.mw_comp[j])
                                for j in self._params.component_list
                                             )))
        except AttributeError:
            # If constraint fails, clean up so that DAE can try again later
            self.del_component(self.enth_mass)
            self.del_component(self.mixture_enthalpy_eqn)
            raise

    def get_material_flow_terms(b, p, j):
        return b.flow_mass*b.mass_frac_comp[j]

    def get_enthalpy_flow_terms(b, p):
        return b.flow_mass*b.enth_mass

    def get_material_density_terms(b, p, j):
        return (1 - b._params.particle_porosity) * (
            b.dens_mass_sol*b.mass_frac_comp[j])

    def get_energy_density_terms(b, p):
        return (1 - b._params.particle_porosity)*b.dens_mass_sol*b.enth_mass

    def define_state_vars(b):
        return {"flow_mass": b.flow_mass,
                "temperature": b.temperature,
                "mass_frac_comp": b.mass_frac_comp}

    def get_material_flow_basis(b):
        return MaterialFlowBasis.mass

    def model_check(blk):
        """
        Model checks for property block
        """
        # Check temperature bounds
        if value(blk.temperature) < blk.temperature.lb:
            _log.error('{} Temperature set below lower bound.'
                       .format(blk.name))
        if value(blk.temperature) > blk.temperature.ub:
            _log.error('{} Temperature set above upper bound.'
                       .format(blk.name))
