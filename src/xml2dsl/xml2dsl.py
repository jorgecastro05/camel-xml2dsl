import configargparse
from lxml import etree, objectify
from rich import console
from rich.console import Console
import importlib.metadata
import re

__version__ = importlib.metadata.version('camel-xml2dsl')
ns = {"camel": "http://camel.apache.org/schema/spring"}
console = Console()

class Converter:
    def __init__(self):
        self.dsl_route = ''

    def xml_to_dsl(self):
        p = configargparse.ArgParser(
            description="Transforms xml routes to dsl routes " + __version__)
        p.add_argument('--xml', metavar='xml', type=str,
                       help='xml camel context file', required=True, env_var='XML_CTX_INPUT')
        p.add_argument('--beans', metavar='beans', type=str,
                       help='use beans instead processors', required=False, env_var='USE_BEANS')
        args = p.parse_args()
        with open(args.xml, "r") as xml_file:
            parser = etree.XMLParser(remove_comments=True)
            data = objectify.parse(xml_file, parser=parser)
            console.log(" XML 2 DSL Utility ", style="bold red")
            root = data.getroot()
            for camelContext in root.findall('camel:camelContext', ns):
                if 'id' in camelContext.attrib:
                    console.log("processing camel context", camelContext.attrib['id'])
                self.get_namespaces(camelContext)
                self.dsl_route = self.analyze_node(camelContext)
                print("dsl route:\n", self.dsl_route)

    def get_namespaces(self, node):
        console.log("namespaces:", node.nsmap)

    def analyze_node(self, node):
        dslText = ""
        for child in node:
            node_name = child.tag.partition('}')[2] + "_def"
            console.log("procesing node", node_name, child.tag, child.sourceline)
            dslText += getattr(self, node_name)(child)
        return dslText

    def analyze_element(self, node):
        node_name = node.tag.partition('}')[2] + "_def"
        console.log("procesing node", node_name, node.tag, node.sourceline)
        return getattr(self, node_name)(node)

    def route_def(self, node):
        route_def = self.analyze_node(node)
        route_def += "\n.end();\n"
        return route_def

    def propertyPlaceholder_def(self, node):
        return ""

    def dataFormats_def(self, node):
        return '\n//TODO: define dataformat ' + node[0].tag + '\n'

    def endpoint_def(self, node):
        return ""

    def multicast_def(self, node):
        multicast_def = "\n.multicast()"
        multicast_def += self.analyze_node(node)
        multicast_def += "\n.end() //end multicast"
        return multicast_def
    
    def bean_def(self, node):
        if 'method' in node.attrib:
            return '\n.bean("' + node.attrib['ref'] + '","'+ node.attrib['method'] + '")'
        elif 'beanType' in node.attrib:
            return '\n.bean("' + node.attrib['ref'] + '","'+ node.attrib['beanType'] + '")'
        else:
            return '\n.bean("' + node.attrib['ref'] + '")'

    def aggregator_def(self, node):
        return "//TODO: Aggregator"
    
    def recipientList_def(self, node):
        recipient_def = "\n.recipientList()."
        recipient_def += self.analyze_node(node)
        recipient_def += ".end() // end recipientList"
        return recipient_def

    def errorHandler_def(self, node):
        if node.attrib['type'] == "DefaultErrorHandler":
            return "\ndefaultErrorHandler().setRedeliveryPolicy(policy);"

    def redeliveryPolicyProfile_def(self, node):
        policy_def = "\nRedeliveryPolicy policy = new RedeliveryPolicy()"
        if "maximumRedeliveries" in node.attrib:
            policy_def += ".maximumRedeliveries("+ node.attrib["maximumRedeliveries"]+")"
        if "retryAttemptedLogLevel" in node.attrib:
            policy_def += ".retryAttemptedLogLevel(LoggingLevel." + node.attrib["retryAttemptedLogLevel"] +")"
        if "redeliveryDelay" in node.attrib:
            policy_def += ".redeliveryDelay("+ node.attrib["redeliveryDelay"] +")"
        if "logRetryAttempted" in node.attrib:
            policy_def += ".logRetryAttempted("+node.attrib["logRetryAttempted"] +")"
        if  "logRetryStackTrace" in node.attrib:
            policy_def += ".logRetryStackTrace("+node.attrib["logRetryStackTrace"]+")"
        policy_def += ";"
        return policy_def


    def onException_def(self, node):
        exceptions = []
        for exception in node.findall("camel:exception", ns):
            exceptions.append(exception.text + ".class")
            node.remove(exception)
        exceptions = ','.join(exceptions)
        onException_def = '\nonException(' + exceptions + ')'
        handled = node.find("camel:handled", ns)
        if handled is not None:
            onException_def += '.handled(' + handled[0].text + ')'
            node.remove(handled)
        redeliveryPolicy = node.find("camel:redeliveryPolicy", ns)
        if redeliveryPolicy is not None:
            onException_def += '\n.maximumRedeliveries('+redeliveryPolicy.attrib['maximumRedeliveries'] + \
                ')' if 'maximumRedeliveries' in redeliveryPolicy.attrib else ""
            onException_def += '\n.redeliveryDelay('+redeliveryPolicy.attrib['redeliveryDelay'] + \
                ')' if 'redeliveryDelay' in redeliveryPolicy.attrib else ""
            onException_def += '\n.retryAttemptedLogLevel(LoggingLevel.' + \
                redeliveryPolicy.attrib['retryAttemptedLogLevel'] + \
                ')' if 'retryAttemptedLogLevel' in redeliveryPolicy.attrib else ""
            onException_def += '\n.retriesExhaustedLogLevel(LoggingLevel.' + \
                redeliveryPolicy.attrib['retriesExhaustedLogLevel'] + \
                ')' if 'retriesExhaustedLogLevel' in redeliveryPolicy.attrib else ""
            node.remove(redeliveryPolicy)
        if "redeliveryPolicyRef" in node.attrib:
            onException_def += ".redeliveryPolicy(policy)"    
        onException_def += self.analyze_node(node)
        onException_def += "\n.end();\n"
        return onException_def

    def description_def(self, node):
        if node.text:
           return "//" + node.text + "\n"
        else:
            return ""

    def from_def(self, node):
        routeId = node.getparent().attrib['id']
        routeFrom = node.attrib['uri']
        from_def = '\nfrom("' + routeFrom+'").routeId("' + routeId + '")'
        from_def += self.analyze_node(node)
        return from_def

    def log_def(self, node):
        if 'loggingLevel' in node.attrib and node.attrib['loggingLevel'] != 'INFO' :
            return '\n.log(LoggingLevel.' + node.attrib['loggingLevel'] + ', "' + self.deprecatedProcessor(node.attrib['message']) + '")'
        else:
            return '\n.log("' + self.deprecatedProcessor(node.attrib['message']) + '")'

    def choice_def(self, node):
        choice_def = '\n.choice() //' + str(node.sourceline)
        choice_def += self.analyze_node(node)
        parent = node.getparent()
        if parent.tag != '{'+ns['camel']+'}route':
            choice_def += "\n.endChoice() //" + str(node.sourceline)
        else:
            choice_def += "\n.end() //end choice " + str(node.sourceline)
        return choice_def

    def when_def(self, node):
        return '\n.when().' + self.analyze_node(node)

    def otherwise_def(self, node):
        return '\n.otherwise()' + self.analyze_node(node)

    def simple_def(self, node):
        simple_def = ""
        if node.text is not None:
            simple_def = 'simple("' + self.deprecatedProcessor(node.text) + '")'
        else:
            simple_def = 'simple("")'
        if "resultType" in node.attrib:
            simple_def += ".resultType("+ node.attrib["resultType"]+".class)"
        return simple_def

    def constant_def(self, node):
        return 'constant("' + node.text + '")'

    def groovy_def(self, node):
        text = node.text.replace('"','\'')
        return 'groovy("' + text + '")'

    def xpath_def(self, node):
        xpath_def = 'xpath("' + node.text + '")'
        if 'resultType' in node.attrib:
            xpath_def = 'xpath("' + node.text + '",' + \
                node.attrib['resultType']+'.class)'
        if 'saxon' in node.attrib:
            xpath_def += '.saxon()'
        return xpath_def

    def to_def(self, node):
        if 'pattern' in node.attrib and 'InOnly' in node.attrib['pattern']:
            return '\n.inOnly("' + self.componentOptions(node.attrib['uri']) + '")'
        else:
            return '\n.to("' + self.componentOptions(node.attrib['uri']) + '")'

    def setBody_def(self, node):
        setBody_predicate = self.analyze_element(node[0])
        return '\n.setBody(' + setBody_predicate + ')'

    def convertBodyTo_def(self, node):
        return '\n.convertBodyTo('+ node.attrib['type'] + '.class)'

    def unmarshal_def(self, node):
        if 'ref' in node.attrib:
            return '\n.unmarshal("' + node.attrib['ref']+ '") //TODO: define dataformat'
        else:
            return '\n.unmarshal()' + self.analyze_node(node)

    def marshal_def(self, node):
        if 'ref' in node.attrib:
            return '\n.marshal("' + node.attrib['ref']+ '") //TODO: define dataformat'
        else:    
            return '\n.marshal()' + self.analyze_node(node)

    def jaxb_def(self, node):
        if 'prettyPrint' in node.attrib:
            return '.jaxb("' + node.attrib['contextPath']+'")'
        else:
            return '.jaxb("' + node.attrib['contextPath']+'")'

    def setHeader_def(self, node):
        setHeader_predicate = self.analyze_element(node[0])
        return '\n.setHeader("'+node.attrib['headerName']+'",' + setHeader_predicate+')'

    def setProperty_def(self, node):
        setProperty_predicate = self.analyze_element(node[0])
        return '\n.setProperty("' + node.attrib['propertyName']+'",' + setProperty_predicate + ')'

    def process_def(self, node):
        return '\n.process("' + node.attrib["ref"]+'")'

    def inOnly_def(self, node):
        return '\n.inOnly("' + node.attrib["uri"]+'")'

    def split_def(self, node):
        split_def = '\n.split().'
        split_def += self.analyze_element(node[0])
        if 'streaming' in node.attrib:
            split_def += '.streaming()'
        if 'strategyRef' in node.attrib:
            split_def += '.aggregationStrategyRef("' + node.attrib["strategyRef"] + '")'
        if 'parallelProcessing' in node.attrib:
            split_def += '.parallelProcessing()'
        node.remove(node[0]) # remove first child as was processed
        split_def += self.analyze_node(node)
        split_def += '\n.end() //end split'
        return split_def

    def removeHeaders_def(self, node):
        if 'excludePattern' in node.attrib:
            return '\n.removeHeaders("' + node.attrib['pattern']+'", "' + node.attrib['excludePattern']+'")'
        else:
            return '\n.removeHeaders("' + node.attrib['pattern']+'")'

    def removeHeader_def(self, node):
        return '\n.removeHeaders("' + node.attrib['headerName']+'")'
        

    def xquery_def(self, node):
        return 'xquery("'+ node.text +'") //xquery not finished please review'

    def doTry_def(self, node):
        doTry_def = "\n.doTry()"
        doTry_def += self.analyze_node(node)
        return doTry_def

    def doCatch_def(self, node):
        exceptions = []
        for exception in node.findall("camel:exception", ns):
            exceptions.append(exception.text + ".class")
            node.remove(exception)
        exceptions = ','.join(exceptions)
        doCatch_def = '\n.endDoTry()'
        doCatch_def += '\n.doCatch(' + exceptions + ')'
        doCatch_def += self.analyze_node(node)
        doCatch_def += "\n.end() //end doCatch"
        return doCatch_def

    def handled_def(self, node):
        return '.handled(' + node[0].text + ')'

    def transacted_def(self, node):
        return ""

    def wireTap_def(self, node):
        if 'executorServiceRef' in node.attrib:
            return '\n.wireTap("'+ node.attrib['uri'] +'").executorServiceRef("profile")'
        else:    
            return '\n.wireTap("'+ node.attrib['uri'] +'")'

    def language_def(self, node):
        return 'language("'+ node.attrib['language']+'","'+ node.text +'")'

    def threads_def(self, node):
        threads_def = None
        maxPoolSize = node.attrib['maxPoolSize'] if 'maxPoolSize' in node.attrib else None
        poolSize = node.attrib['poolSize'] if 'poolSize' in node.attrib else None
        if poolSize is None and maxPoolSize is not None:
            poolSize = maxPoolSize
        if poolSize is not None and maxPoolSize is None:
            maxPoolSize = poolSize
        if 'threadName' in node.attrib:
            threads_def = '\n.threads('+ poolSize+','+ maxPoolSize+',"'+ node.attrib['threadName']+'")'
        else:
            threads_def = '\n.threads('+ poolSize+','+ maxPoolSize+')'

        threads_def += self.analyze_node(node)
        threads_def += "\n.end() //end threads"
        return threads_def

    def delay_def(self, node):
        delay_def = '\n.delay().'
        delay_def += self.analyze_node(node)
        return delay_def

    def javaScript_def(self, node):
        return 'new JavaScriptExpression("'+ node.text +'")'

    def threadPoolProfile_def(self, node):
        profileDef = '\nThreadPoolProfile profile = new ThreadPoolProfile();'
        if 'defaultProfile' in node.attrib:
            profileDef += '\nprofile.setDefaultProfile('+ node.attrib['defaultProfile']+');'
        if 'id' in node.attrib:
            profileDef += '\nprofile.setId("'+ node.attrib['id']+'");'
        if 'keepAliveTime' in node.attrib:
            profileDef += '\nprofile.setKeepAliveTime('+ node.attrib['keepAliveTime']+'L);'
        if 'maxPoolSize' in node.attrib:
            profileDef += '\nprofile.setMaxPoolSize('+ node.attrib['maxPoolSize'] +');'
        if 'maxQueueSize' in node.attrib:
            profileDef += '\nprofile.setMaxQueueSize('+ node.attrib['maxQueueSize']+');'
        if 'poolSize' in node.attrib:
            profileDef += '\nprofile.setPoolSize('+ node.attrib['poolSize']+');'
        if 'rejectedPolicy' in node.attrib:
            if node.attrib['rejectedPolicy'] == 'Abort':
                profileDef += '\nprofile.setRejectedPolicy(ThreadPoolRejectedPolicy.Abort);'
        return profileDef

    def throwException_def(self, node):
        throwException_def = ''
        if 'ref' in node.attrib:
            throwException_def = '\n.throwException(Exception.class, "' + node.attrib['ref']+ '")  //TODO: Please review throwException has changed with java DSL'
        else:
            throwException_def = '\n.throwException(Exception.class, "") //TODO: Please review throwException has changed with java DSL'
        throwException_def += self.analyze_node(node)
        return throwException_def

    def spel_def(self, node):
        return 'SpelExpression.spel("' + node.text + '")'

    def loop_def(self, node):
        loop_def = '\n.loop().'
        loop_def += self.analyze_node(node)
        loop_def += '\n.end() // end loop'
        return loop_def
        

    # Text deprecated processor for camel deprecated endpoints and features
    def deprecatedProcessor(self, text):
        text = re.sub('\${property\.(\w+\.?\w+)}', r'${exchangeProperty.\1}', text) #exhange property in simple expressions
        text = re.sub('"', "'", text) # replace all ocurrences from " to '
        text = re.sub('\n', "", text) # remove all endlines
        return text

    # Text processor for apply custom options in to endpoints
    def componentOptions(self, text):
        if "velocity:" in text:
            text += "?contentCache=true"
        return text


if __name__ == "__main__":
    converter = Converter()
    converter.xml_to_dsl()


def main():
    converter = Converter()
    converter.xml_to_dsl()
