import laptimesim
import time
import os
import numpy as np
import matplotlib.pyplot as plt
import pickle

def main(track_opts: dict,
         solver_opts: dict,
         driver_opts: dict,
         sa_opts: dict,
         debug_opts: dict) -> laptimesim.src.lap.Lap:

    # get repo path
    repo_path = os.path.dirname(os.path.abspath(__file__))

    # INITIALIZATION ---------------------------------------------------------------------------------------------------

    output_path = os.path.join(repo_path, "laptimesim", "output")

    output_path_velprofile = os.path.join(output_path, "velprofile")
    os.makedirs(output_path_velprofile, exist_ok=True)

    output_path_testobjects = os.path.join(output_path, "testobjects")
    os.makedirs(output_path_testobjects, exist_ok=True)

    if debug_opts["use_plot_comparison_tph"]:
        output_path_veh_dyn_info = os.path.join(output_path, "veh_dyn_info")
        os.makedirs(output_path_veh_dyn_info, exist_ok=True)

    # CREATE TRACK INSTANCE --------------------------------------------------------------------------------------------

    parfilepath = os.path.join(repo_path, "laptimesim", "input", "tracks", "track_pars.ini")

    if not track_opts["use_pit"]:  # normal case
        trackfilepath = os.path.join(repo_path, "laptimesim", "input", "tracks", "racelines",
                                     track_opts["trackname"] + ".csv")

    else:  # case pit
        trackfilepath = os.path.join(repo_path, "laptimesim", "input", "tracks", "racelines",
                                     track_opts["trackname"] + "_pit.csv")

    # set velocity limit
    if driver_opts["vel_lim_glob"] is not None:
        vel_lim_glob = driver_opts["vel_lim_glob"]
    elif solver_opts["series"] == "FE":
        vel_lim_glob = 225.0 / 3.6
    else:
        vel_lim_glob = np.inf

    # create instance
    track = laptimesim.src.track.Track(pars_track=track_opts,
                                       parfilepath=parfilepath,
                                       trackfilepath=trackfilepath,
                                       vel_lim_glob=vel_lim_glob,
                                       yellow_s1=driver_opts["yellow_s1"],
                                       yellow_s2=driver_opts["yellow_s2"],
                                       yellow_s3=driver_opts["yellow_s3"])

    # debug plot
    if debug_opts["use_debug_plots"]:
        # check if track map exists and set path accordingly
        mapfolderpath = os.path.join(repo_path, "laptimesim", "input", "tracks", "maps")
        mapfilepath = ""

        for mapfile in os.listdir(mapfolderpath):
            if track_opts["trackname"] in mapfile:
                mapfilepath = os.path.join(mapfolderpath, mapfile)
                break

        if debug_opts["use_track_plots"]:
            track.plot_trackmap(mapfilepath=mapfilepath)
            track.plot_curvature()

        # recalculate raceline based on curvature
        track.check_track()

    # ------------------------------------------------------------------------------------------------------------------
    # CREATE CAR INSTANCE ----------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    parfilepath = os.path.join(repo_path, "laptimesim", "input", "vehicles", solver_opts["vehicle"])

    # create instance
    if solver_opts["series"] == "F1":
        car = laptimesim.src.car_hybrid.CarHybrid(parfilepath=parfilepath)
    elif solver_opts["series"] == "FE":
        car = laptimesim.src.car_electric.CarElectric(parfilepath=parfilepath)
    else:
        raise IOError("Unknown racing series!")

    # debug plot
    if debug_opts["use_debug_plots"] and debug_opts["use_track_plots"]:
        # plot tire force potential characteristics
        car.plot_tire_characteristics()

        # plot engine power characteristics
        if car.powertrain_type == "combustion":
            car.plot_power_engine()

   
    driver = laptimesim.src.driver.Driver(carobj=car,
                                          pars_driver=driver_opts,
                                          trackobj=track,
                                          stepsize=track.stepsize)

    lap = laptimesim.src.lap.Lap(driverobj=driver,
                                 trackobj=track,
                                 pars_solver=solver_opts,
                                 debug_opts=debug_opts)

    # ------------------------------------------------------------------------------------------------------------------
    # CALL SOLVER ------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    # save start time
    t_start = time.perf_counter()

    # call simulation
    if not sa_opts["use_sa"]:
        # normal simulation --------------------------------------------------------------------------------------------
        lap.simulate_lap()

        # debug plot
        if debug_opts["use_debug_plots"]:
            
            if debug_opts["use_track_plots"]:
                lap.plot_torques()
                lap.plot_tire_loads()
                lap.plot_enginespeed_gears()

            # plot lateral acceleration profile
            lap.plot_lat_acc()

            # plot tire load profile
            lap.plot_tire_loads()

            # plot aero forces
            lap.plot_aero_forces()

            # plot engine speed and gear selection
            lap.plot_enginespeed_gears()

    else:
        # sensitivity analysis -----------------------------------------------------------------------------------------

        if debug_opts["use_print"]:
            print("INFO: Performing sensitivity analysis!")

        # turn debug messages off
        lap.pars_solver["print_debug"] = False

        # create parameter ranges
        sa_range_1 = np.linspace(sa_opts["range_1"][0], sa_opts["range_1"][1], sa_opts["range_1"][2])
        # if sa_opts["range_2"] is not None:
        #     sa_range_2 = np.linspace(sa_opts["range_2"][0], sa_opts["range_2"][1], sa_opts["range_2"][2])

        # perform analysis
        if sa_opts["sa_type"] == "mass":
            sa_t_lap = np.zeros(sa_opts["range_1"][2])
            sa_energy_cons_kWh = np.zeros(sa_opts["range_1"][2])

            for i, cur_mass in enumerate(sa_range_1):
                print("SA: Starting solver run (%i)" % (i + 1))

                # change mass of vehicle
                lap.driverobj.carobj.pars_general["m"] = cur_mass

                # simulate lap and save lap time
                lap.simulate_lap()
                sa_t_lap[i] = lap.t_cl[-1]
                sa_energy_cons_kWh[i] = lap.es_cl[-1]

                # reset lap
                lap.reset_lap()

                print("SA: Finished solver run (%i)" % (i + 1))
        # new----------------------------------------------------------

        elif sa_opts["sa_type"] == "coast":
            sa_t_lap = np.zeros(sa_opts["range_1"][2])
            sa_energy_cons_kWh = np.zeros(sa_opts["range_1"][2])

            for i, cur_coast in enumerate(sa_range_1):
                print("SA: Starting solver run (%i)" % (i + 1))

                # change coasting
                lap.driverobj.pars_driver["lift_coast_dist"]  = cur_coast
                lap.reset_lap()
                

                lap.simulate_lap()
                sa_t_lap[i] = lap.t_cl[-1]
                sa_energy_cons_kWh[i] = lap.es_cl[-1] / -3600000.0

                #lap.reset_lap()

                print(f"SA: Finished solver run ({i + 1}) with coasting {cur_coast:.1f} m and lap time {sa_t_lap[i]:.1f} s and fuel consumption {sa_energy_cons_kWh[i]:.1f} kWh")

        else:
            sa_t_lap = np.zeros((sa_opts["range_1"][2], sa_opts["range_2"][2]))
            # TODO: implementation of COG and aero variation missing

    # ------------------------------------------------------------------------------------------------------------------
    # EXPORT -----------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    # print to command window
    if not sa_opts["use_sa"] and debug_opts["use_print_result"]:
        print("-" * 50)
        print("Forward/Backward Plus Solver")
        print("Solver runtime: %.2f s" % (time.perf_counter() - t_start))
        print("-" * 50)
        print("Lap time: %.3f s" % lap.t_cl[-1])
        print("S1: %.3f s  |  S2: %.3f s  |  S3: %.3f s" %
              (lap.t_cl[track.zone_inds["s12"]],
               lap.t_cl[track.zone_inds["s23"]] - lap.t_cl[track.zone_inds["s12"]],
               lap.t_cl[-1] - lap.t_cl[track.zone_inds["s23"]]))
        print("-" * 50)
        v_tmp = lap.vel_cl[0] * 3.6
        print("Start velocity: %.1f km/h" % v_tmp)
        v_tmp = lap.vel_cl[-1] * 3.6
        print("Final velocity: %.1f km/h" % v_tmp)
        v_tmp = (lap.vel_cl[0] - lap.vel_cl[-1]) * 3.6
        print("Delta: %.1f km/h" % v_tmp)
        print("-" * 50)
        print("Length of lap: %.2f km" % (lap.trackobj.dists_cl[-1] /1000 ))
        print("Average velocity: %.2f km/h" % (lap.trackobj.dists_cl[-1] / lap.t_cl[-1] * 3.6))
        print("Consumption with and without regen: %.2f kJ/lap | %.2f kJ/lap" % (lap.es_cl[-1]/-1000.0, lap.e_cons_cl[-1] / 1000.0)) # [J] -> [kJ]
        print("Consumption with and without regen: %.2f kWh/lap | %.2f kWh/lap" % (lap.es_cl[-1]/-3600000, lap.e_cons_cl[-1] / 3600000.0)) # [J] -> [kJ]
        print("Consumption avg: %.2f kWh/100km" % (lap.es_cl[-1] / 3600000.0 / (lap.trackobj.dists_cl[-1] / 1000.0) * -100.0)) 
        print("-" * 50)

    elif debug_opts["use_print_result"]:
        print("-" * 50)
        print("Forward/Backward Plus Solver")
        print("Runtime for sensitivity analysis: %.2f s" % (time.perf_counter() - t_start))
        print("-" * 50)

        if sa_opts["sa_type"] == "mass":
            m_diff = sa_range_1[-1] - sa_range_1[0]
            t_lap_diff = sa_t_lap[-1] - sa_t_lap[0]
            fuel_cons_diff = sa_energy_cons_kWh[-1] - sa_energy_cons_kWh[0]

            print("Average sensitivity of lap time to mass: %.3f s/kg" % (t_lap_diff / m_diff))
            print("Average sensitivity of fuel consumption to mass: %.5f kWh/kg" % (fuel_cons_diff /( m_diff )))   
            print("-" * 50)
        elif sa_opts["sa_type"] == "coast":
            coast_diff = sa_range_1[-1] - sa_range_1[0]
            t_lap_diff = sa_t_lap[-1] - sa_t_lap[0]
            fuel_cons_diff = sa_energy_cons_kWh[-1] - sa_energy_cons_kWh[0]

            print("Average sensitivity of lap time to coast dist: %.3f s/m" % (t_lap_diff / coast_diff))
            print("Average sensitivity of fuel consumption to coast dist: %.5f kWh/m" % (fuel_cons_diff /( coast_diff )))   
            print("-" * 50)
        else:
            pass
            # TODO: implementation of COG and aero variation missing

    # write velocity profile output
    output_path = os.path.join(output_path_velprofile, "velprofile_" + track_opts["trackname"].lower() + ".csv")

    tmp_data = np.column_stack((lap.trackobj.dists_cl[:-1], lap.vel_cl[:-1]))

    with open(output_path, "wb") as fh:
        np.savetxt(fh, tmp_data, fmt="%.5f,%.5f", header="distance_m,vel_mps")

    # ------------------------------------------------------------------------------------------------------------------
    # PLOTS ------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    if not sa_opts["use_sa"]:
        if debug_opts["use_plot"]:
            lap.plot_overview()
            # lap.plot_revs_gears()

    else:
        if sa_opts["sa_type"] == "mass":
            # lap time
            fig = plt.figure()
            ax = fig.add_subplot(111)
            ax.plot(sa_range_1, sa_t_lap, "x")
            ax.set_xlim(sa_range_1[0], sa_range_1[-1])
            ax.set_ylim(sa_t_lap[0], sa_t_lap[-1])
            ax.set_title("SA of lap time to mass")
            ax.set_xlabel("mass m in kg")
            ax.set_ylabel("lap time t in s")
            plt.grid()
            plt.show(block=False)

            # fuel consumption
            fig = plt.figure()
            ax = fig.add_subplot(111)
            ax.plot(sa_range_1, sa_energy_cons_kWh, "x")
            ax.set_xlim(sa_range_1[0], sa_range_1[-1])
            ax.set_ylim(sa_energy_cons_kWh[0], sa_energy_cons_kWh[-1])
            ax.set_title("SA of fuel consumption to mass")
            ax.set_xlabel("mass m in kg")
            ax.set_ylabel("fuel consumption in KWh/lap")
            plt.grid()
            plt.show()
            
        if sa_opts["sa_type"] == "coast":
            # same as above but for coasting
            
            fig = plt.figure()

            # First subplot for lap time
            ax1 = fig.add_subplot(211)
            ax1.plot(sa_range_1, sa_t_lap, "x")
            ax1.set_xlim(sa_range_1[0], sa_range_1[-1])
            ax1.set_ylim(sa_t_lap[0], sa_t_lap[-1])
            ax1.set_title("SA of lap time to coast dist")
            ax1.set_xlabel("coast in m")
            ax1.set_ylabel("lap time t in s")
            ax1.grid()

            # Second subplot for fuel consumption
            ax2 = fig.add_subplot(212)
            ax2.plot(sa_range_1, sa_energy_cons_kWh, "x")
            ax2.set_xlim(sa_range_1[0], sa_range_1[-1])
            ax2.set_ylim(sa_energy_cons_kWh[0], sa_energy_cons_kWh[-1])
            ax2.set_title("SA of fuel consumption to coast m")
            ax2.set_xlabel("coast in m ")
            ax2.set_ylabel("fuel consumption in kWh/lap")
            ax2.grid()

            plt.show()


    # ------------------------------------------------------------------------------------------------------------------
    # CI TESTING -------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    # pickle lap object for possible CI testing
    result_objects_file_path = os.path.join(output_path_testobjects,
                                            "testobj_laptimesim_" + track_opts["trackname"] + ".pkl")
    with open(result_objects_file_path, 'wb') as fh:
        pickle.dump(lap, fh)

    return lap  # return required in case of CI testing


# ----------------------------------------------------------------------------------------------------------------------
# MAIN FUNCTION CALL ---------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------

if __name__ == '__main__':

    # ------------------------------------------------------------------------------------------------------------------
    # USER INPUT -------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------

    # F1 qualifying mode:   DRS activated, EM strategy FCFB, initial_energy 4.0MJ, full power of 575kW
    # F1 race mode:         DRS as desired, EM strategy LBP, initial_energy 0.0MJ, power reduced to 546kW (-5%)
    # FE qualifying mode:   DRS deactivated, EM strategy FCFB
    # FE race mode:         DRS deactivated, EM strategy FCFB + lift&coast
    # tracks must be unclosed, i.e. last point != first point!

    # track options ----------------------------------------------------------------------------------------------------
    # trackname:            track name of desired race track (file must be available in the input folder)
    # flip_track:           switch to flip track direction if required
    # mu_weather:           [-] factor to consider wet track, e.g. by mu_weather = 0.6
    # interp_stepsize_des:  [m], desired stepsize after interpolation of the input raceline points
    # curv_filt_width:      [m] window width of moving average filter -> set None for deactivation
    # use_drs1:             DRS zone 1 switch
    # use_drs2:             DRS zone 2 switch
    # use_pit:              activate pit stop (requires _pit track file!)

    track_opts_ = {"trackname": "Hockenheim",
                   "flip_track": False,
                   "mu_weather": 1.0,
                   "interp_stepsize_des": 3.0,
                   "curv_filt_width": 6.0,
                   "use_drs1": False,
                   "use_drs2": False,
                   "use_pit": False}

    # solver options ---------------------------------------------------------------------------------------------------
    # vehicle:                  vehicle parameter file
    # series:                   F1, FE
    # limit_braking_weak_side:  can be None, 'FA', 'RA', 'all' -> set if brake force potential should be determined
    #                           based on the weak (i.e. inner) side of the car, e.g. when braking into a corner
    # v_start:                  [m/s] velocity at start
    # find_v_start:             determine the real velocity at start
    # max_no_em_iters:          maximum number of iterations for EM recalculation
    # es_diff_max:              [J] stop criterion -> maximum difference between two solver runs

    solver_opts_ = {"vehicle": "BEV_Taycan.ini",
                    "series": "FE",
                    "limit_braking_weak_side": 'RA',
                    "v_start": 150.0 / 3.6,
                    "find_v_start": True,
                    "max_no_em_iters": 20,
                    "es_diff_max": 1.0}

    # driver options ---------------------------------------------------------------------------------------------------
    # vel_subtr_corner: [m/s] velocity subtracted from max. cornering vel. since drivers will not hit the maximum
    #                   perfectly
    # vel_lim_glob:     [m/s] velocity limit, set None if unused
    # yellow_s1:        yellow flag in sector 1
    # yellow_s2:        yellow flag in sector 2
    # yellow_s3:        yellow flag in sector 3
    # yellow_throttle:  throttle position in a yellow flag sector
    # initial_energy:   [J] initial energy (F1: max. 4 MJ/lap, FE Berlin: 4.58 MJ/lap)
    # em_strategy:      FCFB, LBP, LS, NONE -> FCFB = First Come First Boost, LBP = Longest (time) to Breakpoint,
    #                   LS = Lowest Speed, FE requires FCFB as it only drives in electric mode!
    # use_recuperation: set if recuperation by e-motor and electric turbocharger is allowed or not (lift&coast is
    #                   currently only considered with FCFB)
    # use_lift_coast:   switch to turn lift and coast on/off
    # lift_coast_dist:  [m] lift and coast before braking point

driver_opts_ = {"vel_subtr_corner": 5/3.6,
                "vel_lim_glob": 150.0 /3.6,
                "yellow_s1": True,
                "yellow_s2": True,
                "yellow_s3": True,
                "yellow_throttle": 1.0,
                "initial_energy": 0.0e6,
                "em_strategy": "FCFB",
                "use_recuperation": True,
                "use_lift_coast": True,
                "lift_coast_dist":20.0} # 200m ist je nach Kurve auch etwas viel

    # sensitivity analysis options -------------------------------------------------------------------------------------
    # use_sa:   switch to deactivate sensitivity analysis
    # sa_type:  'mass', 'aero', 'cog'
    # range_1:  range of parameter variation [start, end, number of steps]
    # range_2:  range of parameter variation [start, end, number of steps] -> CURRENTLY NOT IMPLEMENTED

sa_opts_ = {"use_sa": False,
            "sa_type": "coast", 
            "range_1":[10.0, 250.0, 15],
            "range_2": None}

    # debug options ----------------------------------------------------------------------------------------------------
    # use_plot:                 plot results
    # use_debug_plots:          plot additional plots for debugging
    # use_plot_comparison_tph:  calculate velocity profile with TPH FB solver and plot a comparison
    # use_print:                set if prints to console should be used or not (does not suppress hints/warnings)
    # use_print_result:         set if result should be printed to console or not

debug_opts_ = {"use_plot": True,
                "use_debug_plots": True,
                "use_track_plots": True,
                "use_plot_comparison_tph": False,
                "use_print": True,
                "use_print_result": True}

# ###  todo list:
# 
# plot resistance including rolling resistance
# lift and coast not working properly     

# (x) plot longitudinal acceleration
# (x) limit only recuperation power to xy kw
# (x) plot power over time plus and minus recuperation
# (x) add time-constant energy consumption, standby and cooling

# SIMULATION CALL -----------------------------------------

start_time = time.time()

main(track_opts=track_opts_,
         solver_opts=solver_opts_,
         driver_opts=driver_opts_,
         sa_opts=sa_opts_,
         debug_opts=debug_opts_)

print(f"Runtime: {time.time() - start_time:.2f} seconds")
#wait for a key press to keep the plot open
#input("Press any key to exit")
# docker run -it -v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY -v $(pwd):/home/docker/data/s/ sim
