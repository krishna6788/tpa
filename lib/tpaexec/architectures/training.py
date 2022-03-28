#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# © Copyright EnterpriseDB UK Limited 2015-2022 - All rights reserved.

from ..architecture import Architecture

import sys

ISSUE_URL = "https://github.com/EnterpriseDB/tpaexec/issues/"


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

    def update_cluster_tags(self, cluster_tags):
        cluster_tags.update({"Reference": f"{ISSUE_URL}{self.args['issue']}"})