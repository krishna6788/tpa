#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# © Copyright EnterpriseDB UK Limited 2015-2021 - All rights reserved.

from ..architecture import Architecture

import sys

class Training(Architecture):
    def add_architecture_options(self, p, g):
        g.add_argument(
            "--num-instances",
            "--instances",
            type=int,
            metavar="N",
            help="number of instances required",
            dest="num_instances",
            required=True,
        )
        g.add_argument(
            "--redmine-id",
            "--ticket",
            "--issue",
            metavar="N",
            help="Redmine id of issue for this cluster",
            dest="issue",
            required=True,
        )

    def num_locations(self):
        return 1

    def cluster_name(self):
        return "training_%s" % self.args["issue"]

    def subnets(self, num):
        instances = self.num_instances()

        if not self.args.get("subnet") and not self.args.get("subnet_pattern"):
            mask = 28
            if instances > 59:
                print(
                    "ERROR: specify --subnet[-pattern] if you need a /25 or larger subnet",
                    file=sys.stderr,
                )
                sys.exit(-1)
            elif instances > 27:
                mask = 26
            elif instances > 9:
                mask = 27
            self.args["subnet_pattern"] = "10.33.x.x/%s" % str(mask)

        return super().subnets(num)

    def update_cluster_tags(self, cluster_tags):
        cluster_tags.update(
            {
                "Reference": "https://redmine.2ndquadrant.com/issues/%s"
                % self.args["issue"]
            }
        )
