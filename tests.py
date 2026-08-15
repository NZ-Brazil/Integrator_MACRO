"""Tests for the integrator, on a mini case built on the fly.

    python tests.py

They cover what is easy to break when a new card is added: the case is only
touched where it should be, blanks in the data never erase a value, running
twice changes nothing, and a bad answer warns instead of stopping the job.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from macro_scenario import apply_scenario_config
from macro_scenario.data.card24_prices import PRICES
from macro_scenario.data.card30_capacity import CAPACITY, COLUMN
from macro_scenario.data.card33_storage import STORAGE
from macro_scenario.scenario_config import Answer, parse_numeric, read_scenario_config

ASSETS_FULL = (
    "Type,id,edges--edge--investment_cost_25-A,edges--edge--investment_cost_25-B,"
    "edges--edge--investment_cost_25-C,Note\r\n"
    "VRE,solar_1,100,200,,keep\r\n"
    "VRE,solar_2,110,210,,keep\r\n"
)
ASSETS = (
    "Type,id,edges--edge--investment_cost,Note\r\n"
    "VRE,solar_1,999,keep\r\n"
    "VRE,solar_2,999,keep\r\n"
)
FUEL_PRICES = (
    "Time_Index,natgas_price_BR,coal_price_BR,unknown_fuel\n"
    "1,10,5,1\n2,10,5,1\n3,10,5,1\n"
)
CAP_TRAJECTORY = "Year,MACRO_cap_MtCO2e,MAgPIE_cap_MtCO2e\n2025,614,981\n2030,471,805\n"
CO2_EMISSIONS = "Year,CO2_Total\n2025,634911066.2785072\n2030,668507229.426174\n"

WIND_IDS = list(CAPACITY["B"]["wind_onshore"])[:2]
WIND_ASSETS = (
    f"Type,id,{COLUMN},Note\n"
    f"VRE,{WIND_IDS[0]},1,keep\n"
    f"VRE,{WIND_IDS[1]},1,keep\n"
)

HYDRO_RES_FULL = (
    "Type,id,storage--can_expand,storage--constraints--MaxCapacityConstraint,"
    "storage--max_capacity,edges--inflow_edge--can_expand,"
    "edges--inflow_edge--has_capacity,edges--discharge_edge--can_expand,"
    "edges--discharge_edge--constraints--MaxCapacityConstraint,"
    "edges--discharge_edge--max_capacity,"
    "storage--investment_cost_25-B,Note\n"
    "Res,Grande_hydro_res,FALSE,TRUE,900,FALSE,TRUE,FALSE,TRUE,80,1000000,new\n"
    "Res,Grande_hydro_res_existing,FALSE,FALSE,700,FALSE,TRUE,FALSE,FALSE,70,1000000,old\n"
)
HYDRO_RES = (
    "Type,id,storage--can_expand,storage--constraints--MaxCapacityConstraint,"
    "storage--max_capacity,edges--inflow_edge--can_expand,"
    "edges--inflow_edge--has_capacity,edges--discharge_edge--can_expand,"
    "edges--discharge_edge--constraints--MaxCapacityConstraint,"
    "edges--discharge_edge--max_capacity,"
    "storage--investment_cost,Note\n"
    "Res,Grande_hydro_res_existing,FALSE,FALSE,700,FALSE,TRUE,FALSE,FALSE,70,7,old\n"
)
HYDRO_ROR_FULL = (
    "Type,id,edges--elec_edge--can_expand,edges--elec_edge--has_capacity,"
    "edges--elec_edge--constraints--MaxCapacityConstraint,"
    "edges--elec_edge--max_capacity,Note\n"
    "Ror,Grande_hydro_ror,FALSE,TRUE,TRUE,500,new\n"
    "Ror,Grande_hydro_ror_existing,FALSE,TRUE,FALSE,400,old\n"
)
HYDRO_ROR = (
    "Type,id,edges--elec_edge--can_expand,edges--elec_edge--has_capacity,"
    "edges--elec_edge--constraints--MaxCapacityConstraint,"
    "edges--elec_edge--max_capacity,Note\n"
    "Ror,Grande_hydro_ror_existing,FALSE,TRUE,FALSE,400,old\n"
)

COAL = (
    "Type,id,edges--elec_edge--constraints--MinFlowConstraint,"
    "edges--elec_edge--can_expand,edges--elec_edge--has_capacity\n"
    "Coal,BR_CE_Coal_Existing,TRUE,FALSE,TRUE\n"
    "Coal,BR_AC_Coal,TRUE,TRUE,TRUE\n"
)
GAS = (
    "Type,id,edges--elec_edge--constraints--MaxCapacityConstraint,"
    "edges--elec_edge--constraints--MinFlowConstraint,edges--elec_edge--max_capacity,"
    "edges--elec_edge--can_expand,edges--elec_edge--has_capacity\n"
    "Gas,BR_AM_Combined_Cycle_Existing,FALSE,TRUE,591,FALSE,TRUE\n"
    "Gas,BR_Combined_Cycle,TRUE,TRUE,7500,TRUE,TRUE\n"
)
NUCLEAR = (
    "Type,id,edges--elec_edge--constraints--MinFlowConstraint,"
    "edges--elec_edge--can_expand,edges--elec_edge--has_capacity,"
    "edges--elec_edge--lifetime\n"
    "Nuc,BR_RJ_Nuclear_Existing_Angra1,TRUE,FALSE,TRUE,16\n"
    "Nuc,BR_RJ_Nuclear_Existing_Angra2,TRUE,FALSE,TRUE,19\n"
    "Nuc,BR_AC_Nuclear_Large,FALSE,TRUE,FALSE,60\n"
)
ROOFTOP = (
    "Type,id,edges--edge--constraints--MinCapacityConstraint,"
    "edges--edge--min_capacity,edges--edge--can_expand,edges--edge--has_capacity\n"
    "PV,BR_RO_rooftop_pv,TRUE,0,TRUE,TRUE\n"
    "PV,BR_RO_rooftop_pv_mandatoryB,FALSE,30,FALSE,FALSE\n"
    "PV,BR_RO_rooftop_pv_mandatoryC,FALSE,100,FALSE,FALSE\n"
)
UPSTREAM = (
    "Type,id,transforms--emission_rate\n"
    "Up,Gasoline_fossil_Upstream,0.01943\n"
    "Up,Diesel_fossil_Upstream,0.02001\n"
    "Up,JetFuel_fossil_Upstream,0.01943\n"
)

NODES = """{
    "nodes": [
        {
            "type": "CO2",
            "instance_data": [
                {
                    "id": "co2_emitted_BR",
                    "constraints": {
                        "CO2CapConstraint": true
                    },
                    "rhs_policy": {
                        "CO2CapConstraint": 1370500000
                    }
                },
                {
                    "id": "co2_source",
                    "max_supply": [
                        72478.4322235739
                    ],
                    "price_supply": [
                        0
                    ]
                }
            ]
        },
        {
            "type": "CO2Captured",
            "instance_data": [
                {
                    "id": "co2_storage_Parana",
                    "constraints": {
                        "CO2StorageConstraint": true
                    },
                    "rhs_policy": {
                        "CO2StorageConstraint": 332000000
                    }
                },
                {
                    "id": "co2_storage_Ceara",
                    "constraints": {
                        "CO2StorageConstraint": true
                    },
                    "rhs_policy": {
                        "CO2StorageConstraint": 300000
                    }
                }
            ]
        }
    ]
}
"""

PERIODS = ("2025", "2030")


def build_case(root):
    root = Path(root)
    (root / "system").mkdir(parents=True)
    for period in PERIODS:
        (root / f"assets_full/assets_{period}").mkdir(parents=True)
        (root / f"assets/assets_{period}").mkdir(parents=True)
        (root / f"assets_full/assets_{period}/solar.csv").write_text(ASSETS_FULL, newline="")
        (root / f"assets/assets_{period}/solar.csv").write_text(ASSETS, newline="")
        (root / f"assets/assets_{period}/wind_onshore.csv").write_text(WIND_ASSETS, newline="")
        (root / f"assets_full/assets_{period}/hydro_res.csv").write_text(HYDRO_RES_FULL, newline="")
        (root / f"assets_full/assets_{period}/hydro_ror.csv").write_text(HYDRO_ROR_FULL, newline="")
        (root / f"assets/assets_{period}/hydro_res.csv").write_text(HYDRO_RES, newline="")
        (root / f"assets/assets_{period}/hydro_ror.csv").write_text(HYDRO_ROR, newline="")
        (root / f"assets/assets_{period}/coal_power.csv").write_text(COAL, newline="")
        for gas in ("natural_gas_power_cc", "natural_gas_power_sc", "natural_gas_power_ccs"):
            (root / f"assets/assets_{period}/{gas}.csv").write_text(GAS, newline="")
        (root / f"assets/assets_{period}/nuclear_power.csv").write_text(NUCLEAR, newline="")
        (root / f"assets/assets_{period}/rooftop_pv.csv").write_text(ROOFTOP, newline="")
        (root / f"assets/assets_{period}/fossil_fuels_upstream.csv").write_text(UPSTREAM, newline="")
        (root / f"system/fuel_prices_{period}.csv").write_text(FUEL_PRICES, newline="")
        (root / f"system/nodes_{period}.json").write_text(NODES)
    (root / "Emissions_cap_trajectory.csv").write_text(CAP_TRAJECTORY, newline="")
    return root


def build_ep2macro(root):
    root = Path(tempfile.mkdtemp())
    for period in PERIODS:
        for prefix in ("demand", "demand_LF", "elec_demand", "h2_demand"):
            (root / f"{prefix}_{period}.csv").write_text("Time_Index,Demand_X\n1,1\n")
    (root / "CO2_Emissions.csv").write_text(CO2_EMISSIONS, newline="")
    return root


def run(case, answers, **kwargs):
    kwargs.setdefault("logger", lambda message: None)
    return apply_scenario_config("job-test", answers, case, **kwargs)


def answer(variable_id, option):
    return Answer(variable_id=variable_id, option_id=option.upper(),
                  variable_name=f"variable {variable_id}")


def nodes_of(case, period="2025"):
    return json.loads((Path(case) / f"system/nodes_{period}.json").read_text())


def instance(case, node_id, period="2025"):
    for group in nodes_of(case, period)["nodes"]:
        for item in group["instance_data"]:
            if item["id"] == node_id:
                return item
    raise KeyError(node_id)


class CaseTest(unittest.TestCase):
    def setUp(self):
        self.case = build_case(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.case, ignore_errors=True)

    def read(self, relative):
        return (self.case / relative).read_text()


# -- card 25 -------------------------------------------------------------


class Card25Test(CaseTest):
    def test_writes_the_option_column(self):
        report = run(self.case, [answer(25, "b")])
        self.assertEqual(report["status"], "applied")
        self.assertIn("200", self.read("assets/assets_2025/solar.csv"))
        self.assertNotIn("999", self.read("assets/assets_2025/solar.csv"))

    def test_keeps_other_columns_and_line_endings(self):
        run(self.case, [answer(25, "b")])
        raw = (self.case / "assets/assets_2025/solar.csv").read_bytes()
        self.assertIn(b"keep", raw)
        self.assertIn(b"\r\n", raw)  # the file was CRLF and stays CRLF

    def test_empty_option_never_erases(self):
        report = run(self.case, [answer(25, "c")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertIn("999", self.read("assets/assets_2025/solar.csv"))

    def test_unknown_option_warns(self):
        report = run(self.case, [answer(25, "z")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertEqual(report["status"], "applied_with_warnings")


# -- card 27 -------------------------------------------------------------


def hydro(case, name, period="2025"):
    import csv
    path = Path(case) / f"assets/assets_{period}/{name}.csv"
    with open(path, encoding="utf-8-sig") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


class Card27Test(CaseTest):
    def test_option_a_adds_the_candidates_to_both_files(self):
        run(self.case, [answer(27, "a")])
        res, ror = hydro(self.case, "hydro_res"), hydro(self.case, "hydro_ror")
        self.assertEqual(len(res), 2)
        self.assertEqual(len(ror), 2)
        self.assertEqual(res["Grande_hydro_res"]["storage--can_expand"], "FALSE")
        self.assertEqual(res["Grande_hydro_res_existing"]["storage--can_expand"], "FALSE")
        self.assertEqual(ror["Grande_hydro_ror"]["edges--elec_edge--can_expand"], "FALSE")
        self.assertEqual(res["Grande_hydro_res"]["storage--max_capacity"], "900")
        self.assertEqual(res["Grande_hydro_res"]["edges--discharge_edge--max_capacity"], "80")
        self.assertEqual(ror["Grande_hydro_ror"]["edges--elec_edge--max_capacity"], "500")

    def test_option_b_drops_the_reservoir_candidate_only(self):
        run(self.case, [answer(27, "b")])
        self.assertEqual(list(hydro(self.case, "hydro_res")), ["Grande_hydro_res_existing"])
        self.assertEqual(len(hydro(self.case, "hydro_ror")), 2)

    def test_option_c_drops_both_candidates(self):
        run(self.case, [answer(27, "c")])
        self.assertEqual(list(hydro(self.case, "hydro_res")), ["Grande_hydro_res_existing"])
        self.assertEqual(list(hydro(self.case, "hydro_ror")), ["Grande_hydro_ror_existing"])
        self.assertEqual(hydro(self.case, "hydro_res")["Grande_hydro_res_existing"]
                         ["edges--inflow_edge--can_expand"], "FALSE")

    def test_a_then_c_then_a_is_symmetric(self):
        run(self.case, [answer(27, "a")])
        run(self.case, [answer(27, "c")])
        run(self.case, [answer(27, "a")])
        self.assertEqual(len(hydro(self.case, "hydro_res")), 2)

    def test_27_runs_after_25(self):
        report = run(self.case, [answer(27, "a"), answer(25, "b")])
        self.assertEqual([a["variable_id"] for a in report["adjustments"]], ["25", "27"])

    def test_added_rows_take_the_cost_of_the_chosen_25_option(self):
        report = run(self.case, [answer(25, "b"), answer(27, "a")])
        self.assertEqual(hydro(self.case, "hydro_res")["Grande_hydro_res"]
                         ["storage--investment_cost"], "1000000")
        self.assertEqual(report["warnings"], [])

    def test_added_rows_report_a_missing_cost(self):
        report = run(self.case, [answer(27, "a")])  # card 25 not answered
        self.assertEqual(hydro(self.case, "hydro_res")["Grande_hydro_res"]
                         ["storage--investment_cost"], "")
        self.assertTrue(any("storage--investment_cost" in w for w in report["warnings"]))

    def test_existing_rows_keep_their_other_columns(self):
        run(self.case, [answer(27, "a")])
        res = hydro(self.case, "hydro_res")
        self.assertEqual(res["Grande_hydro_res_existing"]["storage--investment_cost"], "7")
        self.assertEqual(res["Grande_hydro_res_existing"]["edges--inflow_edge--has_capacity"], "TRUE")

    def test_check_writes_nothing(self):
        before = self.read("assets/assets_2025/hydro_res.csv")
        run(self.case, [answer(27, "a")], dry_run=True)
        self.assertEqual(before, self.read("assets/assets_2025/hydro_res.csv"))

    def test_a_card_that_fails_halfway_writes_nothing(self):
        # The card edits four files; the last one is gone, so it raises after
        # having staged the first three. None of them may reach disk.
        before = self.read("assets/assets_2025/hydro_res.csv")
        (self.case / "assets/assets_2030/hydro_ror.csv").unlink()
        report = run(self.case, [answer(27, "a")])
        self.assertEqual(report["adjustments"][0]["status"], "key_missing")
        self.assertEqual(before, self.read("assets/assets_2025/hydro_res.csv"))

    def test_a_later_card_still_runs_after_one_fails(self):
        (self.case / "assets/assets_2030/hydro_ror.csv").unlink()
        report = run(self.case, [answer(27, "a"), answer(32, "c")])
        statuses = {a["variable_id"]: a["status"] for a in report["adjustments"]}
        self.assertEqual(statuses["27"], "key_missing")
        self.assertEqual(statuses["32"], "applied")


# -- card 24 -------------------------------------------------------------


class Card24Test(CaseTest):
    def test_broadcasts_the_period_price(self):
        run(self.case, [answer(24, "b")])
        expected = str(PRICES["B"][2030]["natgas_price_BR"])
        self.assertEqual(self.read("system/fuel_prices_2030.csv").count(expected), 3)

    def test_each_period_gets_its_own_price(self):
        run(self.case, [answer(24, "c")])
        first = str(PRICES["C"][2025]["natgas_price_BR"])
        last = str(PRICES["C"][2030]["natgas_price_BR"])
        self.assertIn(first, self.read("system/fuel_prices_2025.csv"))
        self.assertIn(last, self.read("system/fuel_prices_2030.csv"))

    def test_columns_the_case_does_not_price_are_reported(self):
        report = run(self.case, [answer(24, "b")])
        self.assertTrue(any("jetfuel" in note for note in report["notes"]))

    def test_columns_not_in_the_table_are_untouched(self):
        run(self.case, [answer(24, "b")])
        self.assertIn(",1\n", self.read("system/fuel_prices_2025.csv"))  # unknown_fuel

    def test_unknown_option_warns(self):
        report = run(self.case, [answer(24, "d")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertIn("10,5", self.read("system/fuel_prices_2025.csv"))


# -- card 2 --------------------------------------------------------------


class Card2Test(CaseTest):
    def test_cap_is_converted_from_mt_to_t(self):
        run(self.case, [answer(2, "")])
        self.assertEqual(instance(self.case, "co2_emitted_BR")["rhs_policy"]["CO2CapConstraint"],
                         614_000_000)
        self.assertEqual(
            instance(self.case, "co2_emitted_BR", "2030")["rhs_policy"]["CO2CapConstraint"],
            471_000_000)

    def test_missing_trajectory_warns(self):
        (self.case / "Emissions_cap_trajectory.csv").unlink()
        report = run(self.case, [answer(2, "")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertEqual(instance(self.case, "co2_emitted_BR")["rhs_policy"]["CO2CapConstraint"],
                         1370500000)

    def test_node_file_keeps_its_shape(self):
        before = self.read("system/nodes_2025.json")
        run(self.case, [answer(2, "")])
        after = self.read("system/nodes_2025.json")
        self.assertEqual(len(before.splitlines()), len(after.splitlines()))
        self.assertEqual(sum(1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b), 1)


# -- card 33 -------------------------------------------------------------


class Card33Test(CaseTest):
    def test_option_a_turns_the_constraint_off(self):
        run(self.case, [answer(33, "a")])
        parana = instance(self.case, "co2_storage_Parana")
        self.assertFalse(parana["constraints"]["CO2StorageConstraint"])
        self.assertEqual(parana["rhs_policy"]["CO2StorageConstraint"], 332000000)

    def test_option_b_writes_the_allowance_in_every_period(self):
        run(self.case, [answer(33, "b")])
        for period in PERIODS:
            parana = instance(self.case, "co2_storage_Parana", period)
            self.assertTrue(parana["constraints"]["CO2StorageConstraint"])
            self.assertEqual(parana["rhs_policy"]["CO2StorageConstraint"],
                             STORAGE["B"]["co2_storage_Parana"])

    def test_placeholder_basin_is_kept_and_reported(self):
        report = run(self.case, [answer(33, "b")])
        self.assertEqual(instance(self.case, "co2_storage_Ceara")["rhs_policy"]["CO2StorageConstraint"],
                         300000)
        self.assertTrue(any("Ceara" in w for w in report["warnings"]))

    def test_option_c_is_still_pending(self):
        report = run(self.case, [answer(33, "c")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertEqual(instance(self.case, "co2_storage_Parana")["rhs_policy"]["CO2StorageConstraint"],
                         332000000)

    def test_a_then_b_is_symmetric(self):
        run(self.case, [answer(33, "a")])
        run(self.case, [answer(33, "b")])
        parana = instance(self.case, "co2_storage_Parana")
        self.assertTrue(parana["constraints"]["CO2StorageConstraint"])
        self.assertEqual(parana["rhs_policy"]["CO2StorageConstraint"],
                         STORAGE["B"]["co2_storage_Parana"])


# -- card 30 -------------------------------------------------------------


class Card30Test(CaseTest):
    def test_option_b_writes_by_id(self):
        run(self.case, [answer(30, "b")])
        text = self.read("assets/assets_2025/wind_onshore.csv")
        self.assertIn(str(CAPACITY["B"]["wind_onshore"][WIND_IDS[0]]), text)

    def test_option_a_is_still_pending(self):
        report = run(self.case, [answer(30, "a")])
        self.assertEqual(report["adjustments"][0]["status"], "not_in_database")
        self.assertIn(",1,keep", self.read("assets/assets_2025/wind_onshore.csv"))


# -- cards 28, 29, 31, 32 (flag cards) -----------------------------------


def assets(case, name, period="2025"):
    import csv
    path = Path(case) / f"assets/assets_{period}/{name}.csv"
    with open(path, encoding="utf-8-sig") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


class Card28Test(CaseTest):
    def test_option_a_lets_candidates_expand(self):
        run(self.case, [answer(28, "a")])
        coal = assets(self.case, "coal_power")
        self.assertEqual(coal["BR_AC_Coal"]["edges--elec_edge--can_expand"], "TRUE")
        self.assertEqual(coal["BR_CE_Coal_Existing"]["edges--elec_edge--can_expand"], "FALSE")
        self.assertEqual(coal["BR_CE_Coal_Existing"]["edges--elec_edge--has_capacity"], "TRUE")
        gas = assets(self.case, "natural_gas_power_cc")
        self.assertEqual(
            gas["BR_Combined_Cycle"]
            ["edges--elec_edge--constraints--MaxCapacityConstraint"],
            "TRUE",
        )

    def test_option_b_closes_coal_candidates(self):
        run(self.case, [answer(28, "b")])
        self.assertNotIn("BR_AC_Coal", assets(self.case, "coal_power"))

    def test_option_b_keeps_the_existing_plant_running(self):
        run(self.case, [answer(28, "b")])
        coal = assets(self.case, "coal_power")["BR_CE_Coal_Existing"]
        self.assertEqual(coal["edges--elec_edge--has_capacity"], "TRUE")

    def test_option_d_closes_the_gas_candidates_too(self):
        run(self.case, [answer(28, "d")])
        gas = assets(self.case, "natural_gas_power_cc")
        self.assertNotIn("BR_Combined_Cycle", gas)
        self.assertEqual(gas["BR_AM_Combined_Cycle_Existing"]["edges--elec_edge--has_capacity"], "TRUE")

    def test_option_b_leaves_gas_open(self):
        run(self.case, [answer(28, "b")])
        gas = assets(self.case, "natural_gas_power_cc")
        self.assertEqual(gas["BR_Combined_Cycle"]["edges--elec_edge--can_expand"], "TRUE")

    def test_option_b_turns_the_gas_max_constraint_off(self):
        run(self.case, [answer(28, "b")])
        gas = assets(self.case, "natural_gas_power_cc")
        self.assertEqual(
            gas["BR_Combined_Cycle"]["edges--elec_edge--constraints--MaxCapacityConstraint"],
            "FALSE",
        )

    def test_option_c_turns_the_gas_max_constraint_on(self):
        report = run(self.case, [answer(28, "c")])
        gas = assets(self.case, "natural_gas_power_cc")
        self.assertEqual(
            gas["BR_Combined_Cycle"]["edges--elec_edge--constraints--MaxCapacityConstraint"],
            "TRUE",
        )
        self.assertEqual(gas["BR_Combined_Cycle"]["edges--elec_edge--max_capacity"], "5000")
        self.assertEqual(
            gas["BR_AM_Combined_Cycle_Existing"]
            ["edges--elec_edge--constraints--MaxCapacityConstraint"],
            "TRUE",
        )
        self.assertEqual(
            gas["BR_AM_Combined_Cycle_Existing"]["edges--elec_edge--max_capacity"],
            "5000",
        )
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["status"], "applied")


class Card29Test(CaseTest):
    def test_option_a_keeps_the_declared_lifetime(self):
        run(self.case, [answer(29, "a")])
        angra = assets(self.case, "nuclear_power")["BR_RJ_Nuclear_Existing_Angra1"]
        self.assertEqual(angra["edges--elec_edge--lifetime"], "16")
        self.assertEqual(angra["edges--elec_edge--has_capacity"], "TRUE")

    def test_option_a_switches_the_angras_off_when_life_runs_out(self):
        # 2045 and 2050 are outside the two-period mini case, so the rule is
        # checked directly.
        from macro_scenario.cards import card29
        from macro_scenario.cards.base import Context

        ctx = Context(case_dir=self.case, answer=answer(29, "a"), report=None)
        values = card29.build_rule(ctx)("BR_RJ_Nuclear_Existing_Angra1", 2050)
        self.assertEqual(values[card29.LIFETIME], 0)
        self.assertEqual(values[card29.HAS_CAPACITY], "TRUE")
        self.assertEqual(values[card29.MIN_FLOW], "FALSE")

    def test_option_b_extends_and_blocks_new_capacity(self):
        report = run(self.case, [answer(29, "b")])
        nuclear = assets(self.case, "nuclear_power")
        self.assertEqual(nuclear["BR_RJ_Nuclear_Existing_Angra2"]["edges--elec_edge--lifetime"], "35")
        self.assertNotIn("BR_AC_Nuclear_Large", nuclear)
        self.assertEqual(report["warnings"], [])

    def test_option_c_opens_the_candidates(self):
        run(self.case, [answer(29, "c")])
        nuclear = assets(self.case, "nuclear_power")
        self.assertEqual(nuclear["BR_AC_Nuclear_Large"]["edges--elec_edge--has_capacity"], "TRUE")
        self.assertEqual(nuclear["BR_AC_Nuclear_Large"]["edges--elec_edge--can_expand"], "TRUE")
        self.assertEqual(
            nuclear["BR_AC_Nuclear_Large"]["edges--elec_edge--constraints--MaxCapacityConstraint"],
            "TRUE",
        )
        self.assertEqual(nuclear["BR_RJ_Nuclear_Existing_Angra1"]["edges--elec_edge--can_expand"], "FALSE")


class Card31Test(CaseTest):
    def _ids(self, period="2025"):
        return sorted(assets(self.case, "rooftop_pv", period))

    def test_option_a_activates_the_plain_rows(self):
        run(self.case, [answer(31, "a")])
        self.assertEqual(self._ids(), ["BR_RO_rooftop_pv"])
        rooftop = assets(self.case, "rooftop_pv")["BR_RO_rooftop_pv"]
        self.assertEqual(rooftop["edges--edge--has_capacity"], "TRUE")
        self.assertEqual(
            rooftop["edges--edge--constraints--MinCapacityConstraint"], "FALSE"
        )
        self.assertEqual(rooftop["edges--edge--min_capacity"], "0")

    def test_option_b_activates_only_mandatory_b(self):
        run(self.case, [answer(31, "b")])
        self.assertEqual(self._ids(), ["BR_RO_rooftop_pv_mandatoryB"])
        rooftop = assets(self.case, "rooftop_pv")["BR_RO_rooftop_pv_mandatoryB"]
        self.assertEqual(
            rooftop["edges--edge--constraints--MinCapacityConstraint"], "TRUE"
        )
        self.assertEqual(rooftop["edges--edge--min_capacity"], "30")

    def test_option_c_activates_only_mandatory_c(self):
        run(self.case, [answer(31, "c")])
        self.assertEqual(self._ids(), ["BR_RO_rooftop_pv_mandatoryC"])
        rooftop = assets(self.case, "rooftop_pv")["BR_RO_rooftop_pv_mandatoryC"]
        self.assertEqual(
            rooftop["edges--edge--constraints--MinCapacityConstraint"], "TRUE"
        )
        self.assertEqual(rooftop["edges--edge--min_capacity"], "100")

    def test_running_the_same_option_twice_is_idempotent(self):
        run(self.case, [answer(31, "b")])
        report = run(self.case, [answer(31, "b")])
        self.assertEqual(self._ids(), ["BR_RO_rooftop_pv_mandatoryB"])
        self.assertEqual(report["adjustments"][0]["status"], "unchanged")


class Card32Test(CaseTest):
    def test_option_c_writes_the_higher_rates(self):
        run(self.case, [answer(32, "c")])
        up = assets(self.case, "fossil_fuels_upstream")
        self.assertEqual(up["Diesel_fossil_Upstream"]["transforms--emission_rate"], "0.02705")

    def test_options_a_and_b_are_the_case_default(self):
        report = run(self.case, [answer(32, "b")])
        self.assertEqual(report["adjustments"][0]["status"], "unchanged")

    def test_c_then_a_goes_back(self):
        run(self.case, [answer(32, "c")])
        run(self.case, [answer(32, "a")])
        up = assets(self.case, "fossil_fuels_upstream")
        self.assertEqual(up["Gasoline_fossil_Upstream"]["transforms--emission_rate"], "0.01943")


# -- EP2MACRO import -----------------------------------------------------


class Ep2MacroTest(CaseTest):
    def setUp(self):
        super().setUp()
        self.source = build_ep2macro(None)

    def tearDown(self):
        shutil.rmtree(self.source, ignore_errors=True)
        super().tearDown()

    def test_demand_files_are_copied(self):
        report = run(self.case, [], ep2macro_dir=self.source)
        self.assertTrue((self.case / "system/demand_2025.csv").is_file())
        self.assertTrue((self.case / "system/h2_demand_2030.csv").is_file())
        self.assertTrue(any(s["step"] == "ep2macro_demand" for s in report["steps"]))

    def test_co2_emissions_go_into_co2_source(self):
        run(self.case, [], ep2macro_dir=self.source)
        self.assertAlmostEqual(instance(self.case, "co2_source")["max_supply"][0],
                               634911066.2785072)

    def test_check_copies_nothing(self):
        run(self.case, [], ep2macro_dir=self.source, dry_run=True)
        self.assertFalse((self.case / "system/demand_2025.csv").exists())


# -- the run as a whole --------------------------------------------------


class PipelineTest(CaseTest):
    def test_stage_order(self):
        chosen = [answer(24, "b"), answer(30, "b"), answer(25, "b"), answer(33, "b")]
        report = run(self.case, chosen)
        self.assertEqual([a["variable_id"] for a in report["adjustments"]],
                         ["25", "33", "24", "30"])

    def test_idempotent(self):
        chosen = [answer(25, "b"), answer(24, "b"), answer(33, "b"), answer(2, "")]
        first = run(self.case, chosen)
        before = self.read("assets/assets_2025/solar.csv")
        second = run(self.case, chosen)
        self.assertEqual(first["summary"]["applied"], 4)
        self.assertEqual(second["summary"]["applied"], 0)
        self.assertEqual(second["summary"]["unchanged"], 4)
        self.assertEqual(before, self.read("assets/assets_2025/solar.csv"))

    def test_check_writes_nothing(self):
        before = self.read("assets/assets_2025/solar.csv")
        after_nodes = self.read("system/nodes_2025.json")
        report = run(self.case, [answer(25, "b"), answer(33, "b")], dry_run=True)
        self.assertEqual(report["summary"]["applied"], 2)
        self.assertEqual(before, self.read("assets/assets_2025/solar.csv"))
        self.assertEqual(after_nodes, self.read("system/nodes_2025.json"))

    def test_other_models_variables_are_ignored(self):
        report = run(self.case, [answer(4, "b"), answer(25, "b")])
        self.assertEqual(len(report["adjustments"]), 1)
        self.assertTrue(any("not consumed by Macro" in note for note in report["notes"]))

    def test_empty_config_is_skipped(self):
        report = run(self.case, [])
        self.assertEqual(report["status"], "skipped")
        self.assertIn("999", self.read("assets/assets_2025/solar.csv"))

    def test_strict_raises(self):
        with self.assertRaises(Exception):
            run(self.case, [answer(25, "z")], strict=True)

    def test_report_is_json_serializable(self):
        report = run(self.case, [answer(25, "b"), answer(24, "b")], write_report=True)
        on_disk = json.loads((self.case / "adjustments.json").read_text())
        self.assertEqual(on_disk["model"], "macro-energy")
        self.assertEqual(on_disk["summary"]["variables_received"], 2)
        self.assertEqual(report["job_id"], "job-test")


class ConfigTest(unittest.TestCase):
    def test_parse_numeric(self):
        self.assertEqual(parse_numeric("afolu=10;other=5"), {"afolu": 10.0, "other": 5.0})
        self.assertEqual(parse_numeric(""), {})

    def test_reads_the_platform_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario_config.csv"
            path.write_text(
                "variable_id,category,variable_name,answer_type,option_id,option_label,numeric_values\n"
                "2,General assumptions,Net emissions caps,slider,,,afolu=10;other=5\n"
                '5,"Natural vegetation, protected areas",Natural vegetation,option,b,Zero,\n'
                "25,Energy supply system,Energy supply technology innovation,option,b,Mid-range,\n",
                encoding="utf-8",
            )
            answers = read_scenario_config(path)
        self.assertEqual([a.variable_id for a in answers], [2, 5, 25])
        self.assertTrue(answers[0].is_slider)
        self.assertEqual(answers[1].category, "Natural vegetation, protected areas")
        self.assertEqual(answers[2].option_id, "B")  # lowercase in the form, uppercase here

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(read_scenario_config("/does/not/exist.csv"), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
