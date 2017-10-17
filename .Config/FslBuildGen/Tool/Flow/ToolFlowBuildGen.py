#!/usr/bin/env python3

#****************************************************************************************************************************************************
# Copyright (c) 2014 Freescale Semiconductor, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#
#    * Neither the name of the Freescale Semiconductor, Inc. nor the names of
#      its contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#****************************************************************************************************************************************************

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import argparse
from FslBuildGen import Main as MainFlow
from FslBuildGen import PackageListUtil
from FslBuildGen import ParseUtil
from FslBuildGen import PlatformUtil
from FslBuildGen import PluginSharedValues
from FslBuildGen.Build import Builder
from FslBuildGen.BuildExternal import RecipeBuilder
from FslBuildGen.BuildExternal.BuilderConfig import BuilderConfig
from FslBuildGen.Config import Config
from FslBuildGen.Context.GeneratorContext import GeneratorContext
from FslBuildGen.Generator import GeneratorPlugin
from FslBuildGen.Generator import PluginConfig
from FslBuildGen.Log import Log
from FslBuildGen.PackageFilters import PackageFilters
from FslBuildGen.Packages.Package import Package
from FslBuildGen.PackageConfig import PlatformNameString
from FslBuildGen.Tool.AToolAppFlow import AToolAppFlow
from FslBuildGen.Tool.AToolAppFlowFactory import AToolAppFlowFactory
from FslBuildGen.Tool.ToolAppConfig import ToolAppConfig
from FslBuildGen.Tool.ToolAppContext import ToolAppContext
from FslBuildGen.Tool.ToolCommonArgConfig import ToolCommonArgConfig
from FslBuildGen.ToolConfig import ToolConfig

class DefaultValue(object):
    DontBuildRecipes = False
    DryRun = False
    ForceClaimInstallArea = False
    GenType = "default"
    Graph = False
    IgnoreNotSupported = False
    ListBuildVariants = False
    ListVariants = False
    PackageConfigurationType = PluginSharedValues.TYPE_DEFAULT


class LocalToolConfig(ToolAppConfig):
    def __init__(self) -> None:
        super(LocalToolConfig, self).__init__()
        self.DontBuildRecipes = DefaultValue.DontBuildRecipes
        self.DryRun = DefaultValue.DryRun
        self.ForceClaimInstallArea = DefaultValue.ForceClaimInstallArea
        self.GenType = DefaultValue.GenType
        self.Graph = DefaultValue.Graph
        self.IgnoreNotSupported = DefaultValue.IgnoreNotSupported
        self.ListBuildVariants = DefaultValue.ListBuildVariants
        self.ListVariants = DefaultValue.ListVariants
        self.PackageConfigurationType = DefaultValue.PackageConfigurationType


def GetDefaultLocalConfig() -> LocalToolConfig:
    return LocalToolConfig()


class ToolFlowBuildGen(AToolAppFlow):
    def __init__(self, toolAppContext: ToolAppContext) -> None:
        super(ToolFlowBuildGen, self).__init__(toolAppContext)


    def ProcessFromCommandLine(self, args: Any, currentDirPath: str, toolConfig: ToolConfig, userTag: Optional[object]) -> None:
        # Process the input arguments here, before calling the real work function
        localToolConfig = LocalToolConfig()

        # Configure the ToolAppConfig part
        localToolConfig.SetToolAppConfigValues(self.ToolAppContext.ToolAppConfig)

        # Configure the local part
        localToolConfig.DontBuildRecipes = args.DontBuildRecipes
        localToolConfig.DryRun = args.DryRun
        localToolConfig.ForceClaimInstallArea = args.ForceClaimInstallArea
        localToolConfig.GenType = args.GenType
        localToolConfig.Graph = args.graph
        localToolConfig.IgnoreNotSupported = args.IgnoreNotSupported
        localToolConfig.ListBuildVariants = args.ListBuildVariants
        localToolConfig.ListVariants = args.ListVariants
        localToolConfig.PackageConfigurationType = args.type

        self.Process(currentDirPath, toolConfig, localToolConfig)


    def Process(self, currentDirPath: str, toolConfig: ToolConfig, localToolConfig: LocalToolConfig) -> None:
        config = Config(self.Log, toolConfig, localToolConfig.PackageConfigurationType,
                        localToolConfig.BuildVariantsDict, localToolConfig.AllowDevelopmentPlugins)

        if localToolConfig.DryRun:
            config.ForceDisableAllWrite()
        if localToolConfig.IgnoreNotSupported:
            config.IgnoreNotSupported = True

        if localToolConfig.Graph:
            PluginConfig.EnableGraph()

        theFiles = MainFlow.DoGetFiles(config, currentDirPath)

        PluginConfig.SetGeneratorType(localToolConfig.GenType)


        platformGeneratorPlugin = PluginConfig.GetGeneratorPluginById(localToolConfig.PlatformName, True)
        generatorContext = GeneratorContext(config, config.ToolConfig.Experimental, platformGeneratorPlugin)
        packages = MainFlow.DoGenerateBuildFiles(config, theFiles, platformGeneratorPlugin, localToolConfig.BuildPackageFilters)

        # If the platform was manually switched, then check if the build platform is supported,
        # if its not disable recipe building and log a warning
        if localToolConfig.DefaultPlatformName != localToolConfig.PlatformName:
            if not PlatformUtil.TryCheckBuildPlatform(localToolConfig.PlatformName):
                self.Log.DoPrintWarning("Build recipes not supported for '{0}' on this OS".format(localToolConfig.PlatformName))
                localToolConfig.DontBuildRecipes = True


        if localToolConfig.ListVariants or localToolConfig.ListBuildVariants:
            requestedFiles = None if config.IsSDKBuild else theFiles
            if not isinstance(packages, dict):
                self.__DoShowList(packages, requestedFiles, localToolConfig.ListVariants,
                                  localToolConfig.ListBuildVariants, platformGeneratorPlugin)
            else:
                for platformName, platformResult in packages.items():
                    platformPackageList = platformResult[0]
                    if len(platformPackageList) > 0:
                        self.Log.DoPrint("Generator: {0}".format(platformName))
                        try:
                            self.Log.PushIndent()
                            self.__DoShowList(platformPackageList, requestedFiles, localToolConfig.ListVariants,
                                              localToolConfig.ListBuildVariants, platformResult[1])
                        finally:
                            self.Log.PopIndent()
        elif not localToolConfig.DontBuildRecipes:
            if not isinstance(packages, dict):
                self.__DoBuildRecipes(config, generatorContext, packages, localToolConfig.ForceClaimInstallArea)
            else:
                for platformName, platformResult in packages.items():
                    platformPackageList = platformResult[0]
                    if len(platformPackageList) > 0 and PlatformUtil.TryCheckBuildPlatform(platformName):
                        self.Log.DoPrint("Generator: {0}".format(platformName))
                        tempPlatformGeneratorPlugin = PluginConfig.GetGeneratorPluginById(platformName, True)
                        tempGeneratorContext = GeneratorContext(config, config.ToolConfig.Experimental, tempPlatformGeneratorPlugin)
                        try:
                            self.Log.PushIndent()
                            self.__DoBuildRecipes(config, tempGeneratorContext, platformPackageList,  localToolConfig.ForceClaimInstallArea)
                        finally:
                            self.Log.PopIndent()


    def __DoShowList(self, packages: List[Package], requestedFiles: Optional[List[str]], listVariants: bool, listBuildVariants: bool,
                     platformGeneratorPlugin: GeneratorPlugin.GeneratorPlugin) -> None:
        if listVariants:
            topLevelPackage = PackageListUtil.GetTopLevelPackage(packages)
            Builder.ShowVariantList(self.Log, topLevelPackage, requestedFiles, platformGeneratorPlugin)
        if listBuildVariants:
            Builder.ShowBuildVariantList(self.Log, platformGeneratorPlugin)


    def __DoBuildRecipes(self, config: Config, generatorContext: GeneratorContext,
                         packages: List[Package],
                         forceClaimInstallArea: bool) -> None:
        builderConfig = BuilderConfig()
        builderConfig.Settings.ForceClaimInstallArea = forceClaimInstallArea
        RecipeBuilder.BuildPackages(config, generatorContext, builderConfig, packages)


class ToolAppFlowFactory(AToolAppFlowFactory):
    def __init__(self) -> None:
        pass


    def GetTitle(self) -> str:
        return 'FslBuildGen'


    def GetToolCommonArgConfig(self) -> ToolCommonArgConfig:
        argConfig = ToolCommonArgConfig()
        argConfig.AddPlatformArg = True
        argConfig.AllowPlaformAll = True
        argConfig.AllowVSVersion = True
        argConfig.AllowForceClaimInstallArea = True
        argConfig.SupportBuildTime = True
        argConfig.AddBuildVariants = True
        argConfig.AddBuildFiltering = True
        return argConfig


    def AddCustomArguments(self, parser: argparse.ArgumentParser, toolConfig: ToolConfig, userTag: Optional[object]) -> None:
        parser.add_argument('-t', '--type', default=DefaultValue.PackageConfigurationType, choices=[PluginSharedValues.TYPE_DEFAULT, 'sdk'], help='Select generator type')
        parser.add_argument('--graph', action='store_true', help='Generate a dependency graph using dot (requires the graphviz dot executable in path)')
        parser.add_argument('--DryRun', action='store_true', help='No files will be created')
        parser.add_argument('--IgnoreNotSupported', action='store_true', help='try to build things that are marked as not supported')
        parser.add_argument('--GenType', default=DefaultValue.GenType, help='Chose the generator type to use ({0})'.format(", ".join(list(GeneratorPlugin.GENERATOR_TYPES.keys()))))
        parser.add_argument('--ListBuildVariants', action='store_true', help='List all build-variants supported by build and exit')
        parser.add_argument('--ListVariants', action='store_true', help='List all variants supported by build and exit')
        parser.add_argument('--DontBuildRecipes', action='store_true', help='Disable building of recipes')


    def Create(self, toolAppContext: ToolAppContext) -> AToolAppFlow:
        return ToolFlowBuildGen(toolAppContext)