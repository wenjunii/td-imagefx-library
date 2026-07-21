uniform float uMix;
uniform float uMode;
uniform float uOpacity;

layout(location = 0) out vec4 fragColor;

vec3 overlayBlend(vec3 base, vec3 layer)
{
    vec3 low = 2.0 * base * layer;
    vec3 high = 1.0 - 2.0 * (1.0 - base) * (1.0 - layer);
    return mix(low, high, step(vec3(0.5), base));
}

vec3 softLightBlend(vec3 base, vec3 layer)
{
    vec3 dark = base - (1.0 - 2.0 * layer) * base * (1.0 - base);
    vec3 d = mix(((16.0 * base - 12.0) * base + 4.0) * base, sqrt(max(base, 0.0)), step(vec3(0.25), base));
    vec3 light = base + (2.0 * layer - 1.0) * (d - base);
    return mix(dark, light, step(vec3(0.5), layer));
}

vec3 applyMode(vec3 base, vec3 layer, float mode)
{
    if (mode < 0.5) return layer;
    if (mode < 1.5) return base + layer;
    if (mode < 2.5) return base * layer;
    if (mode < 3.5) return 1.0 - (1.0 - base) * (1.0 - layer);
    if (mode < 4.5) return overlayBlend(base, layer);
    if (mode < 5.5) return softLightBlend(base, layer);
    if (mode < 6.5) return abs(base - layer);
    return base + layer - 2.0 * base * layer;
}

void main()
{
    vec2 uv = vUV.st;
    vec4 base = texture(sTD2DInputs[0], uv);
    vec4 layer = texture(sTD2DInputs[1], uv);
    float layerAlpha = clamp(layer.a * uOpacity, 0.0, 1.0);
    vec3 modeColor = applyMode(base.rgb, layer.rgb, floor(uMode + 0.5));
    vec3 rgb = mix(base.rgb, modeColor, layerAlpha);
    float alpha = base.a + layerAlpha * (1.0 - base.a);
    vec4 composite = vec4(rgb, alpha);
    fragColor = TDOutputSwizzle(mix(base, composite, clamp(uMix, 0.0, 1.0)));
}
