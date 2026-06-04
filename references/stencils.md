# Built-in Drawio Stencils

drawio includes built-in icon libraries for cloud providers, networking,
hardware, UML, and many other domains. Use stencil shapes when an editable
drawio-native icon is more appropriate than a bitmap crop.

## Usage

In JSON specs, set `shape` to a drawio stencil id:

```json
{
  "type": "cell",
  "id": "gpu0",
  "x": 10,
  "y": 60,
  "w": 50,
  "h": 42,
  "shape": "stencil:mxgraph.gcp2.gpu",
  "fill": "#388E3C",
  "tc": "#FFFFFF",
  "text": "GPU0",
  "fs": 9
}
```

More examples:

```json
{"type": "cell", "id": "server", "x": 10, "y": 60, "w": 50, "h": 50,
 "shape": "stencil:mxgraph.networks.server", "fill": "#1976D2"}

{"type": "cell", "id": "ec2", "x": 10, "y": 60, "w": 50, "h": 50,
 "shape": "stencil:mxgraph.aws4.ec2Instance", "fill": "#FF9900"}
```

## Common Libraries

- GCP (`gcp2`): compute, GPU, CPU, ML APIs, storage, networking
- AWS (`aws4`): EC2, Lambda, S3, GPU instances, infrastructure
- Azure (`azure`): server, rack, cloud services
- Alibaba Cloud (`alibaba_cloud`): ECS, compute, GPU, serverless
- Networks (`networks`): server, mail server, proxy, virtual server
- IBM / IBM Cloud (`ibm`, `ibm_cloud`): cloud services, AI, analytics
- Kubernetes (`kubernetes`, `kubernetes2`): pod, node, cluster, deployment
- Cisco (`cisco19`): routers, switches, firewalls, servers

## Finding Shape IDs

Check the bundled drawio submodule:

```text
drawio/src/main/webapp/stencils/
drawio/src/main/webapp/shapes/
```

The display name in XML is not always the shape id used in styles. For many
libraries, the most reliable source is the corresponding JS registration file in
`drawio/src/main/webapp/shapes/`.

## Notes

- Stencils define their own geometry; `rounded` often has no effect.
- `fill` works with many, but not all, stencils.
- Text may render inside or over the stencil depending on the shape.
- Test at the final size; some icons lose clarity below 40 px.
- If a source figure uses a detailed custom pictogram that is only a leaf icon,
  a bitmap `image_crop` may be more faithful than a generic stencil.
