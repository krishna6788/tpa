#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# © Copyright EnterpriseDB UK Limited 2015-2021 - All rights reserved.

from .bdr import BDR

import sys


class BDR_Simple(BDR):
    def add_architecture_options(self, p, g):
        g.add_argument(
            "--num-instances",
            type=int,
            metavar="N",
            help="number of BDR instances required",
            dest="num_instances",
            default=3,
        )
        g.add_argument(
            "--bdr-version",
            metavar="VER",
            help="major version of BDR required",
            dest="bdr_version",
            choices=["1", "2", "3"],
        )
        super().add_architecture_options(p, g)

    def num_locations(self):
        return 1

    def update_cluster_vars(self, cluster_vars):
        # We must decide which version of Postgres to install, which version
        # of BDR to install, and which repositories and extensions must be
        # enabled for the combination to work.
        #
        # If --postgres-version is specified, we infer the correct BDR
        # version. If --bdr-version is specified, we infer the correct
        # Postgres version. If both are specified, we check that the
        # combination makes sense.
        #
        # If any --2Q-repositories are specified, we do not interfere with
        # that setting at all.

        tpa_2q_repositories = self.args.get("tpa_2q_repositories") or []
        given_repositories = " ".join(tpa_2q_repositories)
        postgres_version = self.args.get("postgres_version")
        bdr_version = None

        if postgres_version == "9.4":
            bdr_version = self.args.get("bdr_version") or "1"
        elif postgres_version == "9.6":
            bdr_version = self.args.get("bdr_version") or "2"
        elif postgres_version in ["10", "11", "12", "13"]:
            bdr_version = self.args.get("bdr_version") or "3"
        elif postgres_version is None:
            bdr_version = self.args.get("bdr_version")

            if bdr_version is None and tpa_2q_repositories:
                if "/bdr2/" in given_repositories:
                    bdr_version = "2"
                elif "/bdr3/" in given_repositories:
                    bdr_version = "3"

            if bdr_version == "1":
                postgres_version = "9.4"
            elif bdr_version == "2":
                postgres_version = "9.6"
            elif bdr_version in ["3", None]:
                postgres_version = "11"
                bdr_version = "3"

        supported_combinations = [
            ("9.4", "1"),
            ("9.4", "2"),
            ("9.6", "2"),
            ("10", "3"),
            ("11", "3"),
            ("12", "3"),
            ("13", "3"),
        ]

        if (postgres_version, bdr_version) not in supported_combinations:
            print(
                "ERROR: Postgres %s with BDR %s is not supported"
                % (postgres_version, bdr_version),
                file=sys.stderr,
            )
            sys.exit(-1)

        postgresql_flavour = "postgresql"
        extensions = []

        if bdr_version == "1":
            postgresql_flavour = "postgresql-bdr"
        elif bdr_version == "2":
            if not tpa_2q_repositories or "/bdr2/" not in given_repositories:
                tpa_2q_repositories.append("products/bdr2/release")
        elif bdr_version == "3":
            extensions = ["pglogical"]
            if not tpa_2q_repositories:
                flavour = self.args.get("postgresql_flavour") or "postgresql"
                if flavour == "2q":
                    tpa_2q_repositories.append("products/2ndqpostgres/release")
                else:
                    tpa_2q_repositories.append("products/bdr3/release")
                    tpa_2q_repositories.append("products/pglogical3/release")

        postgresql_flavour = self.args.get("postgresql_flavour") or postgresql_flavour

        cluster_vars.update(
            {
                "postgres_coredump_filter": "0xff",
                "postgres_version": postgres_version,
                "postgresql_flavour": postgresql_flavour,
                "extra_postgres_extensions": extensions,
            }
        )

        if tpa_2q_repositories:
            cluster_vars.update(
                {
                    "tpa_2q_repositories": tpa_2q_repositories,
                }
            )
